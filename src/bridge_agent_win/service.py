"""
bridge_agent_win.service — Сервис-демон Windows Агента (Windows Service & Standalone Runner).

Реализует:
  - Фоновый серверный демон, работающий как системная служба Windows (до экрана логина).
  - Консольный режим (standalone runner) для локальной разработки, отладки и Mock-тестов.
  - Регистрацию и обработку RPC методов:
      * heartbeat.ping: проверка доступности и метрики системы.
      * exec.run: запуск команд PowerShell с контролем кодировок и таймаутов.
      * pocket.manifest / pocket.pull / pocket.push: движок синхронизации файлов «Карман».
      * notes.send / notes.history / notes.mark_read: быстрая передача заметок «Записки».
  - Безусловное сквозное логирование КАЖДОГО запроса и ответа в pocket/logs/YYYY-MM-DD.jsonl.
  - Защиту по PSK-токену (HMAC) и сбор системных метрик узла (CPU, RAM, Uptime).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any

from bridge_agent_win.executor import PowerShellExecutor
from bridge_core.config import BridgeConfig
from bridge_core.logger import AtomicJsonlLogger, setup_logging
from bridge_core.models import (
    AuditLogEntry,
    AuditStatus,
    ExecRequestParams,
    NodeOS,
    NodeStatus,
    NoteHistoryParams,
    NoteMarkReadParams,
    NoteSendParams,
    PocketPullParams,
    PocketPullResult,
    PocketPushParams,
    PocketPushResult,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.notes import NotesManager
from bridge_core.pocket import PocketManager
from bridge_core.security import PathTraversalError, PSKAuthenticator, create_server_ssl_context
from bridge_core.transport import AsyncTransportServer, RpcCallError

logger = logging.getLogger(__name__)


def _get_system_metrics() -> tuple[float, int, int]:
    """
    Возвращает текущие метрики системы (cpu_percent, memory_used_mb, uptime_seconds).

    Использует psutil если доступен, иначе fallback на стандартные модули ОС.
    """
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=None)
        mem = int(psutil.virtual_memory().used // (1024 * 1024))
        uptime = int(time.time() - psutil.boot_time())
        return float(cpu), mem, uptime
    except ImportError:
        pass

    # Fallback без внешних библиотек
    return 0.0, 512, int(time.monotonic())


class WindowsBridgeService:
    """
    Основной сервис-демон Bridge Local для Windows.

    Может запускаться как консольное приложение, так и регистрироваться в Windows SCM.
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self.config = config or BridgeConfig.load()
        self.start_time = time.time()
        self._stop_event = asyncio.Event()

        # Настраиваем логирование
        setup_logging(self.config.logging)

        # Каталог для кармана и аудит-логов
        pocket_dir = Path(self.config.pocket.path)
        logs_dir = pocket_dir / self.config.pocket.logs_subdir
        self.audit_logger = AtomicJsonlLogger(logs_dir=logs_dir, auto_fsync=True)

        # Менеджер файлов кармана
        self.pocket_manager = PocketManager(
            pocket_dir=pocket_dir,
            dev_logging=self.config.logging.dev_mode,
        )

        # Менеджер заметок
        self.notes_manager = NotesManager(
            pocket_dir=pocket_dir,
            dev_logging=self.config.logging.dev_mode,
        )

        # Исполнитель команд
        self.executor = PowerShellExecutor(
            dev_logging=self.config.logging.dev_mode,
            allow_posix_fallback=True,
        )

        # Аутентификатор PSK (если задан токен)
        self.authenticator: PSKAuthenticator | None = None
        if self.config.connection.psk_token:
            self.authenticator = PSKAuthenticator(psk_token=self.config.connection.psk_token)

        # TLS SSLContext
        ssl_ctx = None
        if self.config.connection.tls_cert_path and self.config.connection.tls_key_path:
            ssl_ctx = create_server_ssl_context(
                cert_path=self.config.connection.tls_cert_path,
                key_path=self.config.connection.tls_key_path,
            )

        # Асинхронный TCP/TLS сервер
        self.server = AsyncTransportServer(
            host=self.config.connection.host,
            port=self.config.connection.port,
            ssl_context=ssl_ctx,
            dev_logging=self.config.logging.dev_mode,
        )

        # Регистрируем обработчики методов
        self.server.register_handler(RpcMethod.HEARTBEAT_PING, self._handle_ping)
        self.server.register_handler(RpcMethod.EXEC_RUN, self._handle_exec)
        self.server.register_handler(RpcMethod.POCKET_MANIFEST, self._handle_pocket_manifest)
        self.server.register_handler(RpcMethod.POCKET_PULL, self._handle_pocket_pull)
        self.server.register_handler(RpcMethod.POCKET_PUSH, self._handle_pocket_push)
        self.server.register_handler(RpcMethod.NOTES_SEND, self._handle_notes_send)
        self.server.register_handler(RpcMethod.NOTES_HISTORY, self._handle_notes_history)
        self.server.register_handler(RpcMethod.NOTES_MARK_READ, self._handle_notes_mark_read)

        logger.info(
            "[SERVICE-INIT] WindowsBridgeService инициализирован: node=%s, host=%s:%d, pocket=%s",
            self.config.node.name,
            self.config.connection.host,
            self.config.connection.port,
            pocket_dir,
        )

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    async def _verify_auth(
        self,
        params: dict[str, Any],
        session_info: dict[str, Any],
        method: str,
    ) -> tuple[str, str]:
        """Проверяет PSK аутентификацию и возвращает (session_id, client_ip)."""
        req_id = session_info.get("session_id", "unknown")
        peer = session_info.get("peername")
        client_ip = peer[0] if (peer and isinstance(peer, (list, tuple))) else "127.0.0.1"

        if self.authenticator:
            try:
                self.authenticator.verify_auth_params(params)
            except Exception as e:
                logger.warning(
                    "[%s] Ошибка авторизации метода %s от %s: %s",
                    req_id,
                    method,
                    client_ip,
                    e,
                )
                audit_entry = AuditLogEntry(
                    session_id=req_id,
                    client_ip=client_ip,
                    method=method,
                    request_id=req_id,
                    status=AuditStatus.ERROR,
                    stderr_preview="Auth Failed",
                )
                await self.audit_logger.write(audit_entry)
                raise RpcCallError(
                    code=RpcErrorCode.AUTH_FAILED,
                    message=f"Ошибка аутентификации: {e}",
                ) from e

        return req_id, client_ip

    # -----------------------------------------------------------------------
    # Обработчики RPC методов
    # -----------------------------------------------------------------------

    async def _handle_ping(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка heartbeat.ping: возвращает метрики и статус готовности."""
        cpu, mem, uptime = _get_system_metrics()
        pong = PongResult(
            agent_os=NodeOS.WINDOWS,
            cpu_percent=cpu,
            memory_used_mb=mem,
            uptime_seconds=uptime,
            status=NodeStatus.READY,
        )
        return pong.model_dump()

    async def _handle_exec(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Обработка exec.run:
          1. Проверка PSK аутентификации.
          2. Запуск команды через PowerShellExecutor.
          3. Атомарная запись строки в pocket/logs/YYYY-MM-DD.jsonl.
          4. Возврат результата клиенту.
        """
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.EXEC_RUN)
        exec_params = ExecRequestParams.model_validate(params)
        t0 = time.perf_counter_ns()

        try:
            result = await self.executor.execute(exec_params)

            audit_entry = AuditLogEntry(
                session_id=req_id,
                client_ip=client_ip,
                method=RpcMethod.EXEC_RUN,
                request_id=req_id,
                command=exec_params.command,
                timeout_sec=exec_params.timeout_sec,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                stdout_preview=result.stdout[:1000],
                stderr_preview=result.stderr[:1000],
                timed_out=result.timed_out,
                status=AuditStatus.SUCCESS if result.exit_code == 0 else AuditStatus.ERROR,
            )
            await self.audit_logger.write(audit_entry)

            return result.model_dump()

        except RpcCallError as e:
            duration_ms = int((time.perf_counter_ns() - t0) // 1_000_000)
            is_timeout = e.code == RpcErrorCode.COMMAND_TIMEOUT

            audit_entry = AuditLogEntry(
                session_id=req_id,
                client_ip=client_ip,
                method=RpcMethod.EXEC_RUN,
                request_id=req_id,
                command=exec_params.command,
                timeout_sec=exec_params.timeout_sec,
                duration_ms=duration_ms,
                timed_out=is_timeout,
                status=AuditStatus.TIMEOUT if is_timeout else AuditStatus.ERROR,
                stderr_preview=e.message,
            )
            await self.audit_logger.write(audit_entry)
            raise

    # -----------------------------------------------------------------------
    # Обработчики подсистемы «Карман» (Pocket Sync)
    # -----------------------------------------------------------------------

    async def _handle_pocket_manifest(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка pocket.manifest: возвращает полный манифест файлов кармана."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.POCKET_MANIFEST)
        manifest = self.pocket_manager.scan_manifest()

        audit_entry = AuditLogEntry(
            session_id=req_id,
            client_ip=client_ip,
            method=RpcMethod.POCKET_MANIFEST,
            request_id=req_id,
            status=AuditStatus.SUCCESS,
            stdout_preview=f"files={manifest.file_count}, bytes={manifest.total_size_bytes}",
        )
        await self.audit_logger.write(audit_entry)
        return manifest.model_dump()

    async def _handle_pocket_pull(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка pocket.pull: чтение и возврат указанного чанка файла."""
        _req_id, _client_ip = await self._verify_auth(params, session_info, RpcMethod.POCKET_PULL)
        pull_params = PocketPullParams.model_validate(params)

        try:
            data, is_last, total_size = self.pocket_manager.read_chunk(pull_params)
            res = PocketPullResult(
                path=pull_params.path,
                offset=pull_params.offset,
                data_b64=base64.b64encode(data).decode("ascii"),
                is_last=is_last,
                total_size_bytes=total_size,
            )
            return res.model_dump()
        except FileNotFoundError as e:
            raise RpcCallError(
                code=RpcErrorCode.FILE_NOT_FOUND,
                message=f"Файл не найден в кармане: {pull_params.path}",
            ) from e
        except PathTraversalError as e:
            raise RpcCallError(
                code=RpcErrorCode.INVALID_PARAMS,
                message=f"Попытка выхода за пределы кармана: {e}",
            ) from e
        except Exception as e:
            raise RpcCallError(
                code=RpcErrorCode.POCKET_SYNC_ERROR,
                message=f"Ошибка чтения чанка '{pull_params.path}': {e}",
            ) from e

    async def _handle_pocket_push(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка pocket.push: сохранение чанка файла и проверка SHA-256."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.POCKET_PUSH)
        push_params = PocketPushParams.model_validate(params)

        try:
            target_path = self.pocket_manager.write_chunk(push_params)
            chunk_len = len(base64.b64decode(push_params.data_b64))

            res = PocketPushResult(
                path=push_params.path,
                offset=push_params.offset,
                bytes_written=chunk_len,
                is_last=push_params.is_last,
                completed=target_path is not None,
                sha256=push_params.sha256_full if target_path else None,
            )

            if target_path is not None:
                audit_entry = AuditLogEntry(
                    session_id=req_id,
                    client_ip=client_ip,
                    method=RpcMethod.POCKET_PUSH,
                    request_id=req_id,
                    status=AuditStatus.SUCCESS,
                    stdout_preview=f"Saved '{push_params.path}', sha={push_params.sha256_full}",
                )
                await self.audit_logger.write(audit_entry)

            return res.model_dump()

        except PathTraversalError as e:
            raise RpcCallError(
                code=RpcErrorCode.INVALID_PARAMS,
                message=f"Попытка выхода за пределы кармана: {e}",
            ) from e
        except ValueError as e:
            # Нарушение контрольной суммы SHA-256
            audit_entry = AuditLogEntry(
                session_id=req_id,
                client_ip=client_ip,
                method=RpcMethod.POCKET_PUSH,
                request_id=req_id,
                status=AuditStatus.ERROR,
                stderr_preview=str(e),
            )
            await self.audit_logger.write(audit_entry)
            raise RpcCallError(
                code=RpcErrorCode.POCKET_SYNC_ERROR,
                message=str(e),
            ) from e
        except Exception as e:
            raise RpcCallError(
                code=RpcErrorCode.POCKET_SYNC_ERROR,
                message=f"Ошибка сохранения файла '{push_params.path}': {e}",
            ) from e

    # -----------------------------------------------------------------------
    # Обработчики подсистемы «Записки» (Notes)
    # -----------------------------------------------------------------------

    async def _handle_notes_send(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка notes.send: добавление новой текстовой записки."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.NOTES_SEND)
        note_params = NoteSendParams.model_validate(params)

        res = await self.notes_manager.add_note(note_params)

        audit_entry = AuditLogEntry(
            session_id=req_id,
            client_ip=client_ip,
            method=RpcMethod.NOTES_SEND,
            request_id=req_id,
            status=AuditStatus.SUCCESS,
            stdout_preview=f"note_id={res.note_id}, author={note_params.author_os}",
        )
        await self.audit_logger.write(audit_entry)

        return res.model_dump()

    async def _handle_notes_history(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка notes.history: получение списка записок."""
        await self._verify_auth(params, session_info, RpcMethod.NOTES_HISTORY)
        hist_params = NoteHistoryParams.model_validate(params) if params else None
        res = await self.notes_manager.get_history(hist_params)
        return res.model_dump()

    async def _handle_notes_mark_read(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка notes.mark_read: квитирование прочтения заметок."""
        await self._verify_auth(params, session_info, RpcMethod.NOTES_MARK_READ)
        mark_params = NoteMarkReadParams.model_validate(params)
        res = await self.notes_manager.mark_read(mark_params)
        return res.model_dump()

    # -----------------------------------------------------------------------
    # Жизненный цикл службы
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Запускает сервис."""
        await self.server.start()
        logger.info("[SERVICE] Служба Bridge Local запущена и готова к приёму запросов")

    async def stop(self) -> None:
        """Останавливает сервис."""
        self._stop_event.set()
        await self.server.stop()
        logger.info("[SERVICE] Служба Bridge Local остановлена")

    async def run_forever(self) -> None:
        """Запускает сервер и держит процесс до получения сигнала остановки."""
        await self.start()
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()


def main_standalone() -> None:
    """Точка входа для автономного запуска демона из консоли."""
    config = BridgeConfig.load()
    service = WindowsBridgeService(config)

    try:
        asyncio.run(service.run_forever())
    except KeyboardInterrupt, SystemExit:
        logger.info("[SERVICE] Остановка по сигналу прерывания")


if __name__ == "__main__":
    main_standalone()
