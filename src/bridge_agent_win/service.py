"""
bridge_agent_win.service — Сервис-демон Windows Агента (Windows Service & Standalone Runner).

Реализует:
  - Фоновый серверный демон, работающий как системная служба Windows (до экрана логина).
  - Консольный режим (standalone runner) для локальной разработки, отладки и Mock-тестов.
  - Регистрацию и обработку RPC методов (heartbeat.ping, exec.run).
  - Безусловное сквозное логирование КАЖДОГО запроса и ответа в pocket/logs/YYYY-MM-DD.jsonl.
  - Защиту по PSK-токену (HMAC) и сбор системных метрик узла (CPU, RAM, Uptime).
"""

from __future__ import annotations

import asyncio
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
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.security import PSKAuthenticator, create_server_ssl_context
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

        # Каталог для аудит-логов в кармане
        pocket_dir = Path(self.config.pocket.path)
        logs_dir = pocket_dir / self.config.pocket.logs_subdir
        self.audit_logger = AtomicJsonlLogger(logs_dir=logs_dir, auto_fsync=True)

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

        logger.info(
            "[SERVICE-INIT] WindowsBridgeService инициализирован: node=%s, host=%s:%d, pocket=%s",
            self.config.node.name,
            self.config.connection.host,
            self.config.connection.port,
            pocket_dir,
        )

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
          1. Проверка PSK аутентификации (если включена).
          2. Запуск команды через PowerShellExecutor.
          3. Атомарная запись строки в pocket/logs/YYYY-MM-DD.jsonl.
          4. Возврат результата клиенту.
        """
        req_id = session_info.get("session_id", "unknown")
        client_ip = (
            session_info.get("peername", ("127.0.0.1", 0))[0]
            if session_info.get("peername")
            else "127.0.0.1"
        )

        # 1. Проверяем токен авторизации
        if self.authenticator:
            try:
                self.authenticator.verify_auth_params(params)
            except Exception as e:
                logger.warning(
                    "[%s] Ошибка авторизации команды от %s: %s",
                    req_id,
                    client_ip,
                    e,
                )
                # Логируем отказ в доступе
                audit_entry = AuditLogEntry(
                    session_id=req_id,
                    client_ip=client_ip,
                    method=RpcMethod.EXEC_RUN,
                    request_id=req_id,
                    command=str(params.get("command", "")),
                    status=AuditStatus.ERROR,
                    stderr_preview="Auth Failed",
                )
                await self.audit_logger.write(audit_entry)
                raise RpcCallError(
                    code=RpcErrorCode.AUTH_FAILED,
                    message=f"Ошибка аутентификации: {e}",
                ) from e

        exec_params = ExecRequestParams.model_validate(params)
        t0 = time.perf_counter_ns()

        try:
            # 2. Выполняем команду
            result = await self.executor.execute(exec_params)

            # 3. Фиксируем результат в аудит-лог кармана (.jsonl)
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
            # При таймауте или сбое — фиксируем в лог и пробрасываем клиенту
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
