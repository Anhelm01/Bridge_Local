"""
bridge_client_linux.client — Высокоуровневый клиент Bridge Local для Linux.

Инкапсулирует:
  - Управление асинхронным сокетным транспортом (AsyncTransportClient).
  - Аутентификацию по HMAC-SHA256 (PSK) для защищенных сессий.
  - Fail-fast обработку сетевых сбоев, таймаутов и ошибок RPC.
  - Операции удалённого выполнения команд (exec.run).
  - Синхронизацию файлов в кармане (манифесты, чанки, прогресс).
  - Подсистему обмена текстовыми заметками (notes.send, notes.history, notes.mark_read).
  - Мульти-узловую адресацию (source_node, target_node) для масштабируемости F1/F2.
"""

from __future__ import annotations

import base64
import logging
import ssl
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeTimeoutError,
)
from bridge_core.config import BridgeConfig
from bridge_core.models import (
    ExecRequestParams,
    ExecResult,
    NodeOS,
    NoteDeliveryResult,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteMarkReadParams,
    NoteMarkReadResult,
    NoteSendParams,
    PingParams,
    PocketManifestResult,
    PocketPullParams,
    PocketPullResult,
    PocketPushParams,
    PocketPushResult,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.pocket import (
    PocketManager,
    PocketSyncSummary,
    compute_file_sha256,
    sync_pocket,
)
from bridge_core.security import PSKAuthenticator, create_client_ssl_context
from bridge_core.transport import (
    AsyncTransportClient,
    RpcCallError,
    TransportError,
)

logger = logging.getLogger(__name__)


class BridgeClient:
    """
    Высокоуровневый клиент для взаимодействия с агентом Bridge Local.

    Может использоваться как async context manager:
        async with BridgeClient(config) as client:
            pong, rtt = await client.ping()
            res = await client.exec("Get-Process")
    """

    def __init__(
        self,
        config: BridgeConfig | None = None,
        host: str | None = None,
        port: int | None = None,
        psk_token: str | None = None,
        timeout_sec: float | None = None,
        target_node: str | None = None,
        dev_logging: bool | None = None,
    ) -> None:
        self.config = config or BridgeConfig.load()
        self.host = host or self.config.connection.host
        self.port = port if port is not None else self.config.connection.port
        self.timeout_sec = (
            timeout_sec if timeout_sec is not None else self.config.connection.timeout_sec
        )
        self.psk_token = psk_token or self.config.connection.psk_token
        self.source_node = self.config.node.name
        self.target_node = target_node or "win-pc"
        self.dev_logging = dev_logging if dev_logging is not None else self.config.logging.dev_mode

        # Локальный менеджер кармана
        self.pocket_dir = Path(self.config.pocket.path).resolve()
        self.pocket_manager = PocketManager(
            pocket_dir=self.pocket_dir,
            dev_logging=self.dev_logging,
        )

        # Аутентификатор
        self.authenticator: PSKAuthenticator | None = None
        if self.psk_token:
            self.authenticator = PSKAuthenticator(psk_token=self.psk_token)

        # TLS SSLContext
        ssl_ctx: ssl.SSLContext | None = None
        if self.config.connection.tls_cert_path:
            ssl_ctx = create_client_ssl_context(
                ca_cert_path=self.config.connection.tls_cert_path,
                insecure_no_verify=False,
            )

        # Транспорт
        self.transport = AsyncTransportClient(
            host=self.host,
            port=self.port,
            connect_timeout=self.timeout_sec,
            ssl_context=ssl_ctx,
            dev_logging=self.dev_logging,
        )

    # -----------------------------------------------------------------------
    # Управление жизненным циклом соединения
    # -----------------------------------------------------------------------

    async def connect(self) -> None:
        """Устанавливает соединение с агентом."""
        try:
            await self.transport.connect()
        except TransportError as e:
            raise BridgeNetworkError(
                f"Не удалось подключиться к узлу {self.host}:{self.port}: {e}"
            ) from e
        except Exception as e:
            raise BridgeNetworkError(f"Сетевой сбой подключения: {e}") from e

    async def close(self) -> None:
        """Закрывает соединение."""
        await self.transport.close()

    async def __aenter__(self) -> BridgeClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @property
    def is_connected(self) -> bool:
        """Проверяет активность сокетного подключения."""
        return self.transport.is_connected

    # -----------------------------------------------------------------------
    # Базовый защищенный вызов RPC с трансляцией ошибок
    # -----------------------------------------------------------------------

    async def _call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_sec: float | None = None,
        target_node: str | None = None,
    ) -> Any:
        """
        Выполняет RPC-запрос с автоматическим добавлением PSK-аутентификации,
        маршрутизацией узлов и трансляцией низкоуровневых ошибок.
        """
        call_params = dict(params or {})

        # Автоматическое добавление HMAC-заголовка при наличии токена
        if self.authenticator:
            auth_header = self.authenticator.generate_auth_header()
            call_params.update(auth_header)

        dest_node = target_node or self.target_node
        timeout = timeout_sec or self.timeout_sec

        try:
            return await self.transport.call(
                method=method,
                params=call_params,
                timeout_sec=timeout,
                source_node=self.source_node,
                target_node=dest_node,
            )
        except TransportError as e:
            raise BridgeNetworkError(f"Ошибка транспорта: {e}") from e
        except TimeoutError as e:
            raise BridgeTimeoutError(
                f"Превышен таймаут ответа ({timeout} сек) для метода {method}"
            ) from e
        except RpcCallError as e:
            if e.code == RpcErrorCode.AUTH_FAILED:
                raise BridgeAuthError(f"Сбой аутентификации на узле: {e.message}") from e
            if e.code == RpcErrorCode.COMMAND_TIMEOUT:
                raise BridgeTimeoutError(f"Команда превысила лимит времени: {e.message}") from e
            if e.code == RpcErrorCode.NODE_UNREACHABLE:
                raise BridgeNetworkError(f"Целевой узел недоступен: {e.message}") from e
            raise BridgeClientError(f"RPC ошибка [{e.code}]: {e.message}") from e
        except Exception as e:
            raise BridgeClientError(f"Непредвиденная ошибка клиента: {e}") from e

    # -----------------------------------------------------------------------
    # 1. Heartbeat / Liveness Ping
    # -----------------------------------------------------------------------

    async def ping(
        self,
        client_os: NodeOS = NodeOS.LINUX,
        timeout_sec: float | None = None,
        target_node: str | None = None,
    ) -> tuple[PongResult, float]:
        """
        Отправляет heartbeat.ping и замеряет round-trip время в миллисекундах.

        Returns:
            Кортеж (PongResult, latency_ms).
        """
        t0 = time.perf_counter_ns()
        ping_params = PingParams(client_os=client_os)
        raw_result = await self._call(
            RpcMethod.HEARTBEAT_PING,
            params=ping_params.model_dump(),
            timeout_sec=timeout_sec or self.config.heartbeat.timeout_sec,
            target_node=target_node,
        )
        latency_ms = (time.perf_counter_ns() - t0) / 1_000_000
        pong = PongResult.model_validate(raw_result)
        return pong, round(latency_ms, 2)

    # -----------------------------------------------------------------------
    # 2. Удалённое выполнение команд (Exec)
    # -----------------------------------------------------------------------

    async def exec(
        self,
        command: str,
        timeout_sec: int | None = None,
        run_as_admin: bool | None = None,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
        target_node: str | None = None,
    ) -> ExecResult:
        """
        Выполняет команду PowerShell на удаленном узле Windows.

        Returns:
            ExecResult с полями exit_code, stdout, stderr, duration_ms, timed_out.
        """
        req_timeout = timeout_sec or self.config.exec.default_timeout_sec
        is_admin = run_as_admin if run_as_admin is not None else self.config.exec.run_as_admin
        params = ExecRequestParams(
            command=command,
            timeout_sec=req_timeout,
            run_as_admin=is_admin,
            working_dir=working_dir,
            env=env,
            target_node=target_node or self.target_node,
        )

        # Буфер сетевого таймаута: даем процессу завершиться + 5 секунд запаса на сериализацию
        network_timeout = float(req_timeout + 5)

        raw_result = await self._call(
            RpcMethod.EXEC_RUN,
            params=params.model_dump(),
            timeout_sec=network_timeout,
            target_node=target_node,
        )
        return ExecResult.model_validate(raw_result)

    # -----------------------------------------------------------------------
    # 3. Синхронизация кармана (Pocket Storage)
    # -----------------------------------------------------------------------

    async def pocket_manifest(
        self,
        target_node: str | None = None,
    ) -> PocketManifestResult:
        """Получает манифест файлов кармана с удаленного узла."""
        raw_result = await self._call(
            RpcMethod.POCKET_MANIFEST,
            params={},
            target_node=target_node,
        )
        return PocketManifestResult.model_validate(raw_result)

    async def pocket_status(
        self,
        target_node: str | None = None,
    ) -> dict[str, Any]:
        """
        Сравнивает локальный карман с удаленным манифестом и возвращает подробный статус.
        """
        local_manifest = self.pocket_manager.scan_manifest()
        remote_manifest = await self.pocket_manifest(target_node=target_node)
        diff = PocketManager.compare_manifests(local=local_manifest, remote=remote_manifest)

        return {
            "local_path": str(self.pocket_dir),
            "local_files_count": local_manifest.file_count,
            "local_total_bytes": local_manifest.total_size_bytes,
            "remote_files_count": remote_manifest.file_count,
            "remote_total_bytes": remote_manifest.total_size_bytes,
            "to_pull": [f.model_dump() for f in diff.to_pull],
            "to_push": [f.model_dump() for f in diff.to_push],
            "synced": list(diff.synced),
            "is_in_sync": len(diff.to_pull) == 0 and len(diff.to_push) == 0,
        }

    async def pocket_sync(
        self,
        direction: str = "both",
        chunk_size: int = 65536,
        target_node: str | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> PocketSyncSummary:
        """
        Синхронизирует файлы кармана (push, pull или both).

        Args:
            direction: "push", "pull" или "both".
            chunk_size: Размер чанка (по умолчанию 64 КБ).
            target_node: Целевой узел.
            on_progress: Опциональный callback вида (file_path, bytes_transferred, total_bytes).

        Returns:
            PocketSyncSummary со статистикой передачи.
        """
        # Используем существующий проверенный механизм синхронизации из bridge_core
        return await sync_pocket(
            client=self.transport,
            local_manager=self.pocket_manager,
            direction=direction,
            chunk_size=chunk_size,
        )

    async def pocket_push_file(
        self,
        local_file_path: Path | str,
        target_rel_path: str | None = None,
        chunk_size: int = 65536,
        target_node: str | None = None,
    ) -> PocketPushResult:
        """
        Загружает отдельный файл из локальной файловой системы в карман удаленного узла.
        """
        src = Path(local_file_path).resolve()
        if not src.is_file():
            raise BridgeClientError(f"Локальный файл не найден: {src}")

        rel_path = target_rel_path or src.name
        total_size = src.stat().st_size
        offset = 0
        is_last = False
        last_result: PocketPushResult | None = None

        with open(src, "rb") as f:
            while not is_last:
                chunk = f.read(chunk_size)
                offset_before = offset
                offset += len(chunk)
                is_last = offset >= total_size

                push_params = PocketPushParams(
                    path=rel_path,
                    offset=offset_before,
                    data_b64=base64.b64encode(chunk).decode("ascii"),
                    is_last=is_last,
                    sha256_full=compute_file_sha256(src) if is_last else None,
                )
                raw = await self._call(
                    RpcMethod.POCKET_PUSH,
                    params=push_params.model_dump(),
                    target_node=target_node,
                )
                last_result = PocketPushResult.model_validate(raw)

        if not last_result:
            raise BridgeClientError(f"Не удалось отправить файл {src}")
        return last_result

    async def pocket_pull_file(
        self,
        remote_rel_path: str,
        dest_local_path: Path | str | None = None,
        chunk_size: int = 65536,
        target_node: str | None = None,
    ) -> Path:
        """
        Скачивает отдельный файл из удаленного кармана в локальную систему.
        """
        offset = 0
        is_last = False
        dest = (
            Path(dest_local_path).resolve()
            if dest_local_path
            else (self.pocket_dir / remote_rel_path)
        )
        dest.parent.mkdir(parents=True, exist_ok=True)

        part_file = dest.parent / f".{dest.name}.part"
        with open(part_file, "wb") as f:
            while not is_last:
                pull_params = PocketPullParams(
                    path=remote_rel_path,
                    offset=offset,
                    chunk_size=chunk_size,
                )
                raw = await self._call(
                    RpcMethod.POCKET_PULL,
                    params=pull_params.model_dump(),
                    target_node=target_node,
                )
                res = PocketPullResult.model_validate(raw)
                data = base64.b64decode(res.data_b64)
                f.write(data)
                offset += len(data)
                is_last = res.is_last

        part_file.replace(dest)
        return dest

    # -----------------------------------------------------------------------
    # 4. Записки (Notes Engine)
    # -----------------------------------------------------------------------

    async def note_send(
        self,
        text: str,
        target_node: str | None = None,
        author_os: NodeOS = NodeOS.LINUX,
    ) -> NoteDeliveryResult:
        """Отправляет текстовую заметку/ссылку на удаленный узел."""
        params = NoteSendParams(
            text=text,
            author_os=author_os,
            target_node=target_node or self.target_node,
        )
        raw_result = await self._call(
            RpcMethod.NOTES_SEND,
            params=params.model_dump(),
            target_node=target_node,
        )
        return NoteDeliveryResult.model_validate(raw_result)

    async def note_history(
        self,
        limit: int = 50,
        since: str | None = None,
        target_node: str | None = None,
    ) -> NoteHistoryResult:
        """Получает журнал заметок с удаленного узла."""
        params = NoteHistoryParams(limit=limit, since=since)
        raw_result = await self._call(
            RpcMethod.NOTES_HISTORY,
            params=params.model_dump(),
            target_node=target_node,
        )
        return NoteHistoryResult.model_validate(raw_result)

    async def note_mark_read(
        self,
        note_ids: list[str],
        target_node: str | None = None,
    ) -> NoteMarkReadResult:
        """Помечает указанные заметки как прочитанные."""
        params = NoteMarkReadParams(note_ids=note_ids)
        raw_result = await self._call(
            RpcMethod.NOTES_MARK_READ,
            params=params.model_dump(),
            target_node=target_node,
        )
        return NoteMarkReadResult.model_validate(raw_result)

    # -----------------------------------------------------------------------
    # 5. Сводный статус системы (System Status Aggregator)
    # -----------------------------------------------------------------------

    async def get_system_status(self) -> dict[str, Any]:
        """
        Собирает полный статус: пинг, системные метрики, карман, заметки.
        """
        pong, latency_ms = await self.ping()
        pocket_stat = await self.pocket_status()
        notes_hist = await self.note_history(limit=50)

        unread_notes = [n for n in notes_hist.notes if n.status != "read"]

        return {
            "node": {
                "source": self.source_node,
                "target": self.target_node,
                "host": self.host,
                "port": self.port,
            },
            "connection": {
                "status": "online",
                "latency_ms": latency_ms,
                "security": "HMAC-SHA256" if self.psk_token else "open_lan",
            },
            "remote": {
                "os": pong.agent_os.value,
                "status": pong.status.value,
                "cpu_percent": pong.cpu_percent,
                "memory_used_mb": pong.memory_used_mb,
                "uptime_seconds": pong.uptime_seconds,
            },
            "pocket": {
                "local_files": pocket_stat["local_files_count"],
                "local_bytes": pocket_stat["local_total_bytes"],
                "remote_files": pocket_stat["remote_files_count"],
                "remote_bytes": pocket_stat["remote_total_bytes"],
                "in_sync": pocket_stat["is_in_sync"],
                "pending_pull": len(pocket_stat["to_pull"]),
                "pending_push": len(pocket_stat["to_push"]),
            },
            "notes": {
                "total": notes_hist.total_count,
                "unread": len(unread_notes),
            },
        }
