"""
bridge_core.service — Универсальный серверный демон Bridge Local (Universal P2P Node).

Обеспечивает кроссплатформенный запуск RPC-сервера на любой ОС (Linux, Windows, macOS):
  - Регистрация и обработка полного спектра методов JSON-RPC:
      * heartbeat.ping: метрики узла (CPU, RAM, Uptime, NodeOS) и статус готовности.
      * exec.run: удаленный запуск команд через платформенный BaseExecutor (Bash / PowerShell).
      * pocket.*: синхронизация и передача файлов кармана (manifest, pull, push, offset).
      * notes.*: передача и хранение быстрых заметок и ссылок.
      * fs.*: удаленный просмотр каталогов (fs.list, fs.find).
  - Сквозное аудит-логирование каждого вызова в pocket/logs/YYYY-MM-DD.jsonl.
  - Аутентификация запросов по PSK-токену (HMAC + replay protection).
  - LAN Zero-Conf Discovery Responder (UDP 9735).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime
import fnmatch
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from bridge_core.config import BridgeConfig
from bridge_core.discovery import DEFAULT_DISCOVERY_PORT, DiscoveryResponder
from bridge_core.executor import BaseExecutor, create_platform_executor
from bridge_core.logger import AtomicJsonlLogger, setup_logging
from bridge_core.models import (
    AuditLogEntry,
    AuditStatus,
    ExecRequestParams,
    FsEntry,
    FsFindParams,
    FsFindResult,
    FsListParams,
    FsListResult,
    NodeOS,
    NodeStatus,
    NoteHistoryParams,
    NoteMarkReadParams,
    NoteSendParams,
    PocketOffsetParams,
    PocketOffsetResult,
    PocketPullParams,
    PocketPullResult,
    PocketPushParams,
    PocketPushResult,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.notes import NotesManager
from bridge_core.pocket import PocketManager, PocketWatcher
from bridge_core.security import PathTraversalError, PSKAuthenticator, create_server_ssl_context
from bridge_core.transport import AsyncTransportServer, RpcCallError

logger = logging.getLogger(__name__)


def get_system_metrics() -> tuple[float, int, int]:
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

    return 0.0, 512, int(time.monotonic())


class BridgeService:
    """
    Универсальный P2P сервис-демон Bridge Local.
    Работает одинаково на Linux (с BashExecutor) и на Windows (с PowerShellExecutor).
    """

    def __init__(
        self,
        config: BridgeConfig | None = None,
        executor: BaseExecutor | None = None,
        agent_os: NodeOS | None = None,
    ) -> None:
        self.config = config or BridgeConfig.load()
        self.start_time = time.time()
        self._stop_event = asyncio.Event()

        # ОС узла
        if agent_os is not None:
            self.agent_os = agent_os
        else:
            self.agent_os = NodeOS.WINDOWS if sys.platform == "win32" else NodeOS.LINUX

        # Логирование
        setup_logging(self.config.logging)

        # Каталог для кармана и аудит-логов
        pocket_dir = self.config.get_pocket_dir()
        logs_dir = pocket_dir / self.config.pocket.logs_subdir
        self.audit_logger = AtomicJsonlLogger(
            logs_dir=logs_dir,
            auto_fsync=True,
            dev_logging=self.config.logging.dev_mode,
        )

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
        if executor is not None:
            self.executor = executor
        else:
            self.executor = create_platform_executor(dev_logging=self.config.logging.dev_mode)

        # Аутентификатор PSK
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
        bind_host = self.config.connection.host
        if bind_host not in ("127.0.0.1", "localhost", "0.0.0.0"):
            bind_host = "0.0.0.0"

        self.server = AsyncTransportServer(
            host=bind_host,
            port=self.config.connection.port,
            ssl_context=ssl_ctx,
            psk_token=self.config.connection.psk_token,
            dev_logging=self.config.logging.dev_mode,
        )

        # Версионирование и события кармана
        self._pocket_event_id: int = 0
        self._pocket_last_changes: list[str] = []
        self._pocket_change_event = asyncio.Event()
        self.pocket_watcher = PocketWatcher(
            pocket_dir=pocket_dir,
            on_change_callback=self._on_pocket_changed,
            debounce_sec=0.5,
        )

        # Регистрация обработчиков RPC
        self.server.register_handler(RpcMethod.HEARTBEAT_PING, self._handle_ping)
        self.server.register_handler(RpcMethod.EXEC_RUN, self._handle_exec)
        self.server.register_handler(RpcMethod.POCKET_MANIFEST, self._handle_pocket_manifest)
        self.server.register_handler(RpcMethod.POCKET_PULL, self._handle_pocket_pull)
        self.server.register_handler(RpcMethod.POCKET_PUSH, self._handle_pocket_push)
        self.server.register_handler(RpcMethod.POCKET_OFFSET, self._handle_pocket_offset)
        self.server.register_handler(RpcMethod.NOTES_SEND, self._handle_notes_send)
        self.server.register_handler(RpcMethod.NOTES_HISTORY, self._handle_notes_history)
        self.server.register_handler(RpcMethod.NOTES_MARK_READ, self._handle_notes_mark_read)
        self.server.register_handler(RpcMethod.FS_LIST, self._handle_fs_list)
        self.server.register_handler(RpcMethod.FS_FIND, self._handle_fs_find)

        self.monitor_callback: Any = None

        # UDP Discovery Responder
        self.discovery_responder = DiscoveryResponder(
            node_name=self.config.node.name,
            display_name=self.config.node.display_name or "",
            tcp_port=self.config.connection.port,
            psk_token=self.config.connection.psk_token or "",
            pocket_path=str(pocket_dir),
            node_os=self.agent_os.value,
            port=DEFAULT_DISCOVERY_PORT,
        )

        logger.info(
            "[SERVICE-INIT] BridgeService инициализирован: node=%s, OS=%s, host=%s:%d, pocket=%s",
            self.config.node.name,
            self.agent_os.value,
            self.config.connection.host,
            self.config.connection.port,
            pocket_dir,
        )

    def _on_pocket_changed(self, changed_files: list[str]) -> None:
        """Callback от PocketWatcher при изменении файлов в кармане."""
        self._pocket_event_id += 1
        self._pocket_last_changes = changed_files
        self._pocket_change_event.set()
        self._pocket_change_event.clear()
        self.emit_monitor_event(
            "pocket_change",
            {"files": changed_files, "event_id": self._pocket_event_id},
        )

    def emit_monitor_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Отправляет событие мониторинга консоли или трею."""
        if self.monitor_callback is not None:
            with contextlib.suppress(Exception):
                self.monitor_callback(event_type, data)

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

    async def _handle_ping(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка heartbeat.ping: возвращает метрики и статус готовности."""
        cpu, mem, uptime = get_system_metrics()
        pong = PongResult(
            agent_os=self.agent_os,
            cpu_percent=cpu,
            memory_used_mb=mem,
            uptime_seconds=uptime,
            status=NodeStatus.READY,
        )
        peer = session_info.get("peername")
        client_ip = peer[0] if (peer and isinstance(peer, (list, tuple))) else "127.0.0.1"
        self.emit_monitor_event(
            "client_ping",
            {
                "client_ip": client_ip,
                "source_node": params.get("source_node", client_ip),
            },
        )
        return pong.model_dump()

    async def _handle_exec(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка exec.run: выполнение команды через BaseExecutor."""
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
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                status=AuditStatus.SUCCESS if result.exit_code == 0 else AuditStatus.ERROR,
                stdout_preview=result.stdout[:200] if result.stdout else "",
                stderr_preview=result.stderr[:200] if result.stderr else "",
            )
            await self.audit_logger.write(audit_entry)

            self.emit_monitor_event(
                "exec_completed",
                {
                    "client_ip": client_ip,
                    "command": exec_params.command,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                },
            )
            self.emit_monitor_event(
                "exec_done",
                {
                    "client_ip": client_ip,
                    "command": exec_params.command,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                },
            )
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

            self.emit_monitor_event(
                "exec_error",
                {
                    "client_ip": client_ip,
                    "command": exec_params.command,
                    "error": e.message,
                    "duration_ms": duration_ms,
                },
            )
            raise

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
            if pull_params.offset == 0:
                self.emit_monitor_event(
                    "file_requested",
                    {
                        "path": pull_params.path,
                        "total_size": total_size,
                        "client_ip": _client_ip,
                    },
                )
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

                self.emit_monitor_event(
                    "file_received",
                    {
                        "path": push_params.path,
                        "bytes": push_params.offset + chunk_len,
                        "sha256": push_params.sha256_full,
                        "client_ip": client_ip,
                    },
                )

            return res.model_dump()

        except PathTraversalError as e:
            raise RpcCallError(
                code=RpcErrorCode.INVALID_PARAMS,
                message=f"Попытка выхода за пределы кармана: {e}",
            ) from e
        except ValueError as e:
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

    async def _handle_pocket_offset(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка pocket.offset: опрос текущего смещения для докачки файла."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.POCKET_OFFSET)
        offset_params = PocketOffsetParams.model_validate(params)
        offset, part_exists, completed = self.pocket_manager.query_file_offset(offset_params.path)

        res = PocketOffsetResult(
            path=offset_params.path,
            offset=offset,
            part_exists=part_exists,
            completed=completed,
        )
        audit_entry = AuditLogEntry(
            session_id=req_id,
            client_ip=client_ip,
            method=RpcMethod.POCKET_OFFSET,
            request_id=req_id,
            status=AuditStatus.SUCCESS,
            stdout_preview=f"offset={offset}, part={part_exists}, done={completed}",
        )
        await self.audit_logger.write(audit_entry)
        return res.model_dump()

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

        self.emit_monitor_event(
            "note_received",
            {
                "note_id": res.note_id,
                "author_os": str(note_params.author_os),
                "source_node": params.get("source_node") or client_ip,
                "text": note_params.text,
                "received_at": res.received_at,
            },
        )

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

    async def _handle_fs_list(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка fs.list: просмотр содержимого директории."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.FS_LIST)
        list_params = FsListParams.model_validate(params)

        target_path: Path
        if list_params.pocket_only:
            target_path = self.pocket_manager.pocket_dir
        elif list_params.path:
            target_path = Path(list_params.path).expanduser().resolve()
        else:
            target_path = self.pocket_manager.pocket_dir

        if not target_path.exists():
            raise RpcCallError(
                code=RpcErrorCode.FILE_NOT_FOUND,
                message=f"Каталог не найден: {target_path}",
            )
        if not target_path.is_dir():
            raise RpcCallError(
                code=RpcErrorCode.INVALID_PARAMS,
                message=f"Указанный путь не является каталогом: {target_path}",
            )

        entries: list[FsEntry] = []
        try:
            with os.scandir(target_path) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        is_dir = entry.is_dir(follow_symlinks=False)
                        mtime_iso = datetime.datetime.fromtimestamp(
                            stat.st_mtime, tz=datetime.UTC
                        ).isoformat()
                        ext = "" if is_dir else Path(entry.name).suffix
                        entries.append(
                            FsEntry(
                                name=entry.name,
                                path=str(Path(entry.path).resolve()),
                                is_dir=is_dir,
                                size_bytes=stat.st_size if not is_dir else 0,
                                modified_iso=mtime_iso,
                                extension=ext,
                            )
                        )
                        if len(entries) >= list_params.max_items:
                            break
                    except (PermissionError, OSError):
                        continue
        except Exception as e:
            raise RpcCallError(
                code=RpcErrorCode.INTERNAL_ERROR,
                message=f"Ошибка чтения каталога '{target_path}': {e}",
            ) from e

        entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        res = FsListResult(
            target_path=str(target_path),
            total_entries=len(entries),
            entries=entries,
        )

        audit_entry = AuditLogEntry(
            session_id=req_id,
            client_ip=client_ip,
            method=RpcMethod.FS_LIST,
            request_id=req_id,
            status=AuditStatus.SUCCESS,
            stdout_preview=f"Listed {len(entries)} items in '{target_path}'",
        )
        await self.audit_logger.write(audit_entry)
        return res.model_dump()

    async def _handle_fs_find(
        self, params: dict[str, Any], session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработка fs.find: поиск файлов по маске."""
        req_id, client_ip = await self._verify_auth(params, session_info, RpcMethod.FS_FIND)
        find_params = FsFindParams.model_validate(params)

        root_dir = (
            Path(find_params.directory).expanduser().resolve()
            if find_params.directory
            else self.pocket_manager.pocket_dir
        )
        if not root_dir.exists() or not root_dir.is_dir():
            raise RpcCallError(
                code=RpcErrorCode.FILE_NOT_FOUND,
                message=f"Корневой каталог для поиска не найден: {root_dir}",
            )

        found_entries: list[FsEntry] = []
        pattern = find_params.pattern

        try:
            for root, _dirs, files in os.walk(root_dir):
                for fname in files:
                    if fnmatch.fnmatch(fname, pattern):
                        fpath = Path(root) / fname
                        try:
                            st = fpath.stat()
                            mtime_iso = datetime.datetime.fromtimestamp(
                                st.st_mtime, tz=datetime.UTC
                            ).isoformat()
                            found_entries.append(
                                FsEntry(
                                    name=fname,
                                    path=str(fpath.resolve()),
                                    is_dir=False,
                                    size_bytes=st.st_size,
                                    modified_iso=mtime_iso,
                                    extension=fpath.suffix,
                                )
                            )
                            if len(found_entries) >= find_params.max_results:
                                break
                        except (PermissionError, OSError):
                            continue
                if len(found_entries) >= find_params.max_results:
                    break
        except Exception as e:
            raise RpcCallError(
                code=RpcErrorCode.INTERNAL_ERROR,
                message=f"Ошибка поиска в '{root_dir}': {e}",
            ) from e

        res = FsFindResult(
            pattern=pattern,
            searched_directory=str(root_dir),
            total_found=len(found_entries),
            entries=found_entries,
        )

        audit_entry = AuditLogEntry(
            session_id=req_id,
            client_ip=client_ip,
            method=RpcMethod.FS_FIND,
            request_id=req_id,
            status=AuditStatus.SUCCESS,
            stdout_preview=f"Found {len(found_entries)} matches for '{pattern}' in '{root_dir}'",
        )
        await self.audit_logger.write(audit_entry)
        return res.model_dump()

    async def start(self) -> None:
        """Запускает сервис."""
        await self.server.start()
        if self.discovery_responder:
            await self.discovery_responder.start()
        if self.config.pocket.sync_watch:
            self.pocket_watcher.start()
        logger.info(
            "[SERVICE] Служба Bridge Local запущена и готова к приёму запросов (OS=%s, Port=%d)",
            self.agent_os.value,
            self.config.connection.port,
        )

    async def stop(self) -> None:
        """Останавливает сервис."""
        self._stop_event.set()
        if self.discovery_responder:
            self.discovery_responder.stop()
        self.pocket_watcher.stop()
        await self.server.stop()
        logger.info("[SERVICE] Служба Bridge Local остановлена")

    async def run_forever(self) -> None:
        """Запускает сервер и удерживает процесс до получения сигнала остановки."""
        await self.start()
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()
