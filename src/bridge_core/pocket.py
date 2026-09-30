"""
bridge_core.pocket — Подсистема синхронизации файлов «Карман» (Pocket Storage Engine).

Реализует:
  - Автономный файловый транспорт чанками по 64 КБ без сторонних протоколов (SMB, FTP, WebDAV).
  - Сверку контрольных сумм SHA-256 до и после передачи.
  - Атомарную запись через скрытые временные файлы .<filename>.part с os.replace().
  - Защиту от Path Traversal (validate_safe_path).
  - Сканирование и дифференциацию манифестов (compare_manifests).
  - Автоматическое отслеживание изменений через Watchdog с дебаунсом (Debounced Watcher).
  - Подробную Dev-Mode трассировку передачи файлов, смещений и хешей.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bridge_core.models import (
    PocketFileInfo,
    PocketManifestResult,
    PocketPullParams,
    PocketPullResult,
    PocketPushParams,
    PocketPushResult,
    RpcMethod,
)
from bridge_core.retry import retry_with_backoff
from bridge_core.security import validate_safe_path

logger = logging.getLogger(__name__)

# Игнорируемые служебные папки и файлы при сканировании кармана
DEFAULT_IGNORED_NAMES: frozenset[str] = frozenset({"logs", ".git", ".tmp", ".cache", "__pycache__"})


def compute_file_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    """
    Вычисляет контрольную сумму SHA-256 файла потоковым чтением.

    Args:
        path: Путь к файлу.
        chunk_size: Размер блока для потокового чтения (64 КБ).

    Returns:
        Hex-строка хеша длины 64 символа.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class PocketDiffResult:
    """Результат сравнения локального и удалённого манифестов."""

    to_pull: list[PocketFileInfo]  # Файлы, которые нужно скачать с удалённого узла
    to_push: list[PocketFileInfo]  # Файлы, которые нужно отправить на удалённый узел
    synced: list[str]  # Относительные пути идентичных файлов


class PocketManager:
    """
    Менеджер операций с файлами кармана.

    Отвечает за сбор манифеста, чтение/запись чанков и верификацию целостности.
    """

    def __init__(
        self,
        pocket_dir: Path | str,
        ignored_names: frozenset[str] = DEFAULT_IGNORED_NAMES,
        dev_logging: bool = True,
    ) -> None:
        self.pocket_dir = Path(pocket_dir).resolve()
        self.ignored_names = ignored_names
        self.dev_logging = dev_logging
        self.pocket_dir.mkdir(parents=True, exist_ok=True)

    def scan_manifest(self) -> PocketManifestResult:
        """
        Рекурсивно сканирует карман и собирает манифест всех файлов.

        Исключает папку logs/, служебные каталоги и временные файлы *.part.
        """
        t0 = time.perf_counter_ns()
        files: list[PocketFileInfo] = []
        total_size = 0

        for root, dirs, filenames in os.walk(self.pocket_dir):
            # Исключаем нежелательные папки из обхода
            dirs[:] = [d for d in dirs if d not in self.ignored_names and not d.startswith(".")]

            for fname in filenames:
                # Пропускаем скрытые файлы и временные .part файлы
                if fname.startswith(".") or fname.endswith(".part"):
                    continue

                full_path = Path(root) / fname
                try:
                    stat = full_path.stat()
                except OSError:
                    continue

                rel_path = full_path.relative_to(self.pocket_dir).as_posix()
                file_sha = compute_file_sha256(full_path)
                mtime_iso = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()

                info = PocketFileInfo(
                    path=rel_path,
                    sha256=file_sha,
                    size_bytes=stat.st_size,
                    mtime_iso=mtime_iso,
                )
                files.append(info)
                total_size += stat.st_size

        files.sort(key=lambda f: f.path)
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        logger.info(
            "[DEV-POCKET-SCAN] Манифест собран: %d файлов, %d байт (за %.2f мс)",
            len(files),
            total_size,
            elapsed_ms,
        )

        return PocketManifestResult(
            files=files,
            total_size_bytes=total_size,
            file_count=len(files),
        )

    def read_chunk(
        self,
        params: PocketPullParams,
    ) -> tuple[bytes, bool, int]:
        """
        Считывает чанк файла для отправки по сети.

        Args:
            params: Параметры запроса (относительный путь, смещение, размер чанка).

        Returns:
            Кортеж (data_bytes, is_last, total_file_size).

        Raises:
            FileNotFoundError: Если файл не существует.
            PathTraversalError: При попытке выйти за пределы кармана.
        """
        t0 = time.perf_counter_ns()
        target_path = validate_safe_path(self.pocket_dir, params.path)

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Файл '{params.path}' не найден в кармане")

        total_size = target_path.stat().st_size

        def _do_read() -> bytes:
            with open(target_path, "rb") as f:
                f.seek(params.offset)
                return f.read(params.chunk_size)

        data = retry_with_backoff(_do_read, max_retries=5, initial_delay=0.02)

        is_last = (params.offset + len(data)) >= total_size
        elapsed_us = (time.perf_counter_ns() - t0) // 1000

        logger.debug(
            "[DEV-POCKET-READ] Чанк %s: offset=%d, size=%d b, last=%s (%d µs)",
            params.path,
            params.offset,
            len(data),
            is_last,
            elapsed_us,
        )

        return data, is_last, total_size

    def get_part_file(self, rel_path: str) -> Path:
        """Возвращает путь к временному .part файлу для заданного относительного пути."""
        target_path = validate_safe_path(self.pocket_dir, rel_path)
        return target_path.parent / f".{target_path.name}.part"

    def get_partial_offset(self, rel_path: str) -> int:
        """
        Возвращает размер существующего .part файла в байтах (смещение для докачки),
        либо 0 если файл отсутствует.
        """
        part_file = self.get_part_file(rel_path)
        if part_file.exists() and part_file.is_file():
            return part_file.stat().st_size
        return 0

    def query_file_offset(self, rel_path: str) -> tuple[int, bool, bool]:
        """
        Опрашивает статус передачи файла в кармане.

        Returns:
            Кортеж (offset_bytes, part_exists, completed).
        """
        target_path = validate_safe_path(self.pocket_dir, rel_path)
        part_file = target_path.parent / f".{target_path.name}.part"

        if part_file.exists() and part_file.is_file():
            return part_file.stat().st_size, True, False

        if target_path.exists() and target_path.is_file():
            return target_path.stat().st_size, False, True

        return 0, False, False

    def write_chunk(
        self,
        params: PocketPushParams,
    ) -> Path | None:
        """
        Атомарно записывает полученный чанк в файл.

        Запись ведётся во временный скрытый файл `.<name>.part`.
        При получении последнего чанка (`is_last=True`) вычисляется SHA-256,
        сверяется с `sha256_full` и производится атомарное переименование `os.replace`.

        Returns:
            Итоговый Path при успешном завершении файла, либо None если ожидаются ещё чанки.

        Raises:
            ValueError: При несовпадении контрольной суммы SHA-256.
        """
        t0 = time.perf_counter_ns()
        target_path = validate_safe_path(self.pocket_dir, params.path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        part_file = target_path.parent / f".{target_path.name}.part"
        chunk_bytes = base64.b64decode(params.data_b64)

        def _do_write() -> None:
            mode = "r+b" if params.offset > 0 and part_file.exists() else "wb"
            with open(part_file, mode) as f:
                f.seek(params.offset)
                f.write(chunk_bytes)
                f.flush()

        retry_with_backoff(_do_write, max_retries=5, initial_delay=0.02)

        logger.debug(
            "[DEV-POCKET-WRITE] Записан чанк %s: offset=%d, len=%d b, last=%s",
            params.path,
            params.offset,
            len(chunk_bytes),
            params.is_last,
        )

        # Если файл завершён — сверяем хеш и атомарно заменяем целевой файл
        if params.is_last:
            computed_sha = compute_file_sha256(part_file)

            if params.sha256_full and computed_sha != params.sha256_full:
                # Удаляем повреждённый файл
                if part_file.exists():
                    part_file.unlink()
                logger.error(
                    "[POCKET-CORRUPTION] Несовпадение SHA-256 для %s! Ожидалось %s, получено %s",
                    params.path,
                    params.sha256_full,
                    computed_sha,
                )
                raise ValueError(f"Нарушение целостности файла '{params.path}': SHA-256 не совпал")

            # Атомарное перемещение с защитой от Windows Sharing Violation
            def _do_replace() -> None:
                os.replace(part_file, target_path)

            retry_with_backoff(_do_replace, max_retries=5, initial_delay=0.02)

            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
            logger.info(
                "[POCKET-COMPLETE] Файл '%s' успешно принят и проверен (SHA-256: %s, %.2f мс)",
                params.path,
                computed_sha,
                elapsed_ms,
            )
            return target_path

        return None

    @staticmethod
    def compare_manifests(
        local: PocketManifestResult,
        remote: PocketManifestResult,
    ) -> PocketDiffResult:
        """
        Сравнивает два манифеста и определяет файлы для загрузки и отдачи.
        """
        local_map = {f.path: f for f in local.files}
        remote_map = {f.path: f for f in remote.files}

        to_pull: list[PocketFileInfo] = []
        to_push: list[PocketFileInfo] = []
        synced: list[str] = []

        # 1. Проверяем файлы, имеющиеся на удалённом узле
        for path, r_file in remote_map.items():
            l_file = local_map.get(path)
            if l_file is None:
                to_pull.append(r_file)
            elif l_file.sha256 != r_file.sha256:
                # Разрешение конфликтов: выбираем более свежий mtime
                if r_file.mtime_iso > l_file.mtime_iso:
                    to_pull.append(r_file)
                else:
                    to_push.append(l_file)
            else:
                synced.append(path)

        # 2. Проверяем локальные файлы, которых нет на удалённом узле
        for path, l_file in local_map.items():
            if path not in remote_map:
                to_push.append(l_file)

        return PocketDiffResult(to_pull=to_pull, to_push=to_push, synced=synced)


# ---------------------------------------------------------------------------
# Отслеживание изменений кармана (Watchdog с дебаунсом)
# ---------------------------------------------------------------------------


class PocketWatcher:
    """
    Наблюдатель за каталогом кармана.

    Группирует серии файловых событий (дебаунс), чтобы не перегружать сокет
    при пакетном копировании нескольких файлов.
    """

    def __init__(
        self,
        pocket_dir: Path | str,
        on_change_callback: Callable[[list[str]], Any],
        debounce_sec: float = 0.5,
    ) -> None:
        self.pocket_dir = Path(pocket_dir).resolve()
        self.on_change_callback = on_change_callback
        self.debounce_sec = debounce_sec

        self._observer: Any = None
        self._changed_paths: set[str] = set()
        self._debounce_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Запускает отслеживание файловой системы через watchdog."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            self._loop = asyncio.get_running_loop()

            class _Handler(FileSystemEventHandler):
                def __init__(self, watcher: PocketWatcher) -> None:
                    self.watcher = watcher

                def on_any_event(self, event: Any) -> None:
                    # Игнорируем директории и служебные файлы
                    if event.is_directory:
                        return
                    src = getattr(event, "src_path", "")
                    fname = os.path.basename(src)
                    if fname.startswith(".") or fname.endswith(".part"):
                        return
                    if "logs" in src:
                        return

                    self.watcher._schedule_event(src)

            self._observer = Observer()
            self._observer.schedule(_Handler(self), str(self.pocket_dir), recursive=True)
            self._observer.start()
            logger.info("[WATCHDOG] Наблюдение за карманом запущено: %s", self.pocket_dir)

        except Exception as e:
            logger.warning("[WATCHDOG] Не удалось запустить нативный watchdog: %s", e)

    def _schedule_event(self, path: str) -> None:
        """Регистрирует событие изменения и перезапускает таймер дебаунса."""
        if not self._loop:
            return

        def _sync_schedule() -> None:
            self._changed_paths.add(path)
            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
            self._debounce_task = asyncio.create_task(self._debounce_timer())

        self._loop.call_soon_threadsafe(_sync_schedule)

    async def _debounce_timer(self) -> None:
        """Ожидает затишья файловых операций и вызывает коллбэк."""
        try:
            await asyncio.sleep(self.debounce_sec)
            paths = list(self._changed_paths)
            self._changed_paths.clear()

            if paths:
                logger.info(
                    "[WATCHDOG] Обнаружено изменение %d файлов в кармане (после дебаунса)",
                    len(paths),
                )
                res = self.on_change_callback(paths)
                if asyncio.iscoroutine(res):
                    await res
        except asyncio.CancelledError:
            pass

    def stop(self) -> None:
        """Останавливает наблюдатель."""
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None
        if self._debounce_task:
            self._debounce_task.cancel()
            self._debounce_task = None
        logger.debug("[WATCHDOG] Наблюдение остановлено")


# ---------------------------------------------------------------------------
# Клиентский движок синхронизации файлов (Pocket Sync Engine)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PocketSyncSummary:
    """Сводка результатов синхронизации кармана."""

    pulled: list[str]
    pushed: list[str]
    synced: list[str]
    errors: list[str]
    total_bytes_transferred: int
    duration_ms: int


async def sync_pocket(
    client: Any,
    local_manager: PocketManager,
    direction: str = "both",
    chunk_size: int = 65536,
) -> PocketSyncSummary:
    """
    Выполняет синхронизацию файлов между локальным карманом и удалённым агентом.

    Поддерживает режимы:
      - 'both': Двусторонняя синхронизация (с разрешением конфликтов по mtime).
      - 'pull': Только скачивание отсутствующих/обновлённых файлов с удалённого узла.
      - 'push': Только отправка отсутствующих/обновлённых файлов на удалённый узел.

    Args:
        client: Экземпляр AsyncTransportClient с установленным соединением.
        local_manager: Локальный экземпляр PocketManager.
        direction: Направление синхронизации ('both', 'pull', 'push').
        chunk_size: Размер чанка для передачи (по умолчанию 64 КБ).

    Returns:
        PocketSyncSummary со списком переданных файлов и статистикой.
    """
    t0 = time.perf_counter_ns()
    pulled: list[str] = []
    pushed: list[str] = []
    errors: list[str] = []
    total_bytes = 0

    # 1. Получаем удалённый манифест
    remote_data = await client.call(RpcMethod.POCKET_MANIFEST)
    remote_manifest = PocketManifestResult.model_validate(remote_data)

    # 2. Сканируем локальный карман
    local_manifest = local_manager.scan_manifest()

    # 3. Сравниваем манифесты
    diff = PocketManager.compare_manifests(local=local_manifest, remote=remote_manifest)
    logger.info(
        "[POCKET-SYNC-START] Начало синхронизации (direction=%s): pull=%d, push=%d, synced=%d",
        direction,
        len(diff.to_pull),
        len(diff.to_push),
        len(diff.synced),
    )

    # 4. Скачивание (Pull)
    if direction in ("both", "pull"):
        for file_info in diff.to_pull:
            try:
                offset = 0
                is_last = False
                while not is_last:
                    pull_params = PocketPullParams(
                        path=file_info.path,
                        offset=offset,
                        chunk_size=chunk_size,
                    )
                    raw_res = await client.call(
                        RpcMethod.POCKET_PULL,
                        pull_params.model_dump(),
                    )
                    res = PocketPullResult.model_validate(raw_res)

                    push_params = PocketPushParams(
                        path=file_info.path,
                        offset=offset,
                        data_b64=res.data_b64,
                        is_last=res.is_last,
                        sha256_full=file_info.sha256 if res.is_last else None,
                    )
                    local_manager.write_chunk(push_params)

                    chunk_len = len(base64.b64decode(res.data_b64))
                    total_bytes += chunk_len
                    offset += chunk_len
                    is_last = res.is_last

                pulled.append(file_info.path)
                logger.info(
                    "[POCKET-SYNC-PULL] Файл '%s' успешно скачан (%d байт)",
                    file_info.path,
                    file_info.size_bytes,
                )
            except Exception as e:
                err_msg = f"pull '{file_info.path}' error: {e}"
                logger.error("[POCKET-SYNC-ERROR] %s", err_msg)
                errors.append(err_msg)

    # 5. Отправка (Push)
    if direction in ("both", "push"):
        for file_info in diff.to_push:
            try:
                offset = 0
                is_last = False
                while not is_last:
                    pull_params = PocketPullParams(
                        path=file_info.path,
                        offset=offset,
                        chunk_size=chunk_size,
                    )
                    chunk_bytes, is_last, _total_size = local_manager.read_chunk(pull_params)

                    push_params = PocketPushParams(
                        path=file_info.path,
                        offset=offset,
                        data_b64=base64.b64encode(chunk_bytes).decode("ascii"),
                        is_last=is_last,
                        sha256_full=file_info.sha256 if is_last else None,
                    )
                    raw_res = await client.call(
                        RpcMethod.POCKET_PUSH,
                        push_params.model_dump(),
                    )
                    PocketPushResult.model_validate(raw_res)

                    total_bytes += len(chunk_bytes)
                    offset += len(chunk_bytes)

                pushed.append(file_info.path)
                logger.info(
                    "[POCKET-SYNC-PUSH] Файл '%s' успешно отправлен (%d байт)",
                    file_info.path,
                    file_info.size_bytes,
                )
            except Exception as e:
                err_msg = f"push '{file_info.path}' error: {e}"
                logger.error("[POCKET-SYNC-ERROR] %s", err_msg)
                errors.append(err_msg)

    duration_ms = int((time.perf_counter_ns() - t0) // 1_000_000)
    logger.info(
        "[POCKET-SYNC-DONE] Синхронизация завершена: "
        "pulled=%d, pushed=%d, errors=%d, bytes=%d, time=%d ms",
        len(pulled),
        len(pushed),
        len(errors),
        total_bytes,
        duration_ms,
    )

    return PocketSyncSummary(
        pulled=pulled,
        pushed=pushed,
        synced=diff.synced,
        errors=errors,
        total_bytes_transferred=total_bytes,
        duration_ms=duration_ms,
    )
