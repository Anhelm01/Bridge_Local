"""
bridge_agent_win.service — Сервис-демон Windows Агента (Windows Service & Standalone Runner).

Реализует:
  - WindowsBridgeService: субкласс универсального BridgeService, использующий PowerShellExecutor
    и NodeOS.WINDOWS.
  - BridgeLocalAgentWindowsService: системная служба Windows под управлением SCM.
  - main_standalone: консольный раннер для отладки, локального запуска и AgentConsoleMonitor.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    HAS_WIN32SERVICE = True
    _BaseServiceFramework = win32serviceutil.ServiceFramework
except ImportError:
    HAS_WIN32SERVICE = False

    class _BaseServiceFramework:  # type: ignore[no-redef]
        """Базовый заглушечный класс при отсутствии pywin32 (например, на Linux)."""

        def __init__(self, args: list[str]) -> None:
            self.args = args

        def ReportServiceStatus(self, status: int) -> None:  # noqa: N802
            pass


from bridge_agent_win.executor import PowerShellExecutor
from bridge_core.config import BridgeConfig
from bridge_core.models import NodeOS
from bridge_core.service import BridgeService, get_system_metrics

logger = logging.getLogger(__name__)

_get_system_metrics = get_system_metrics


class WindowsBridgeService(BridgeService):
    """
    Основной сервис-демон Bridge Local для Windows.
    Наследует полный RPC-функционал от BridgeService, используя PowerShellExecutor.
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        cfg = config or BridgeConfig.load()
        executor = PowerShellExecutor(
            dev_logging=cfg.logging.dev_mode,
            allow_posix_fallback=True,
        )
        super().__init__(
            config=cfg,
            executor=executor,
            agent_os=NodeOS.WINDOWS,
        )


def main_standalone() -> None:
    """Точка входа для автономного запуска демона из консоли."""
    config = BridgeConfig.load()
    service = WindowsBridgeService(config)

    from bridge_agent_win.monitor import AgentConsoleMonitor, ensure_windows_console_encoding

    ensure_windows_console_encoding()
    monitor = AgentConsoleMonitor(config)
    service.monitor_callback = monitor.on_event

    try:
        monitor.print_banner()

        async def _run_interactive() -> None:
            await service.start()
            monitor.start_interactive_loop(service)
            try:
                await service._stop_event.wait()
            finally:
                await service.stop()
                monitor.stop()

        asyncio.run(_run_interactive())
    except (KeyboardInterrupt, SystemExit):
        logger.info("[SERVICE] Остановка по сигналу прерывания")
    except OSError as e:
        port = getattr(getattr(service, "config", None), "connection", None)
        port_num = port.port if port else 9732
        is_port_in_use = (
            getattr(e, "winerror", None) == 10048
            or getattr(e, "errno", None) == 98
            or "10048" in str(e)
        )
        if is_port_in_use:
            print(f"\n[ERROR] Порт {port_num} уже занят другим процессом!")
            print("       Возможно, служба Windows или другая копия агента уже запущена.")
            print("       Остановите существующий экземпляр или службу перед повторным запуском.")
        else:
            print(f"\n[ERROR] Ошибка сетевого сокета при запуске агента: {e}")
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            with contextlib.suppress(Exception):
                input("\nНажмите Enter для выхода...")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка при работе агента: {e}")
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            with contextlib.suppress(Exception):
                input("\nНажмите Enter для выхода...")
        sys.exit(1)


class BridgeLocalAgentWindowsService(_BaseServiceFramework):  # type: ignore[misc, valid-type]
    """
    Системная служба Windows под управлением SCM (Service Control Manager).

    Позволяет запускать агент до входа пользователя в систему и
    обрабатывать системные сигналы остановки и перезагрузки.
    """

    _svc_name_ = "BridgeLocalAgent"
    _svc_display_name_ = "Bridge Local Windows Daemon"
    _svc_description_ = (
        "Cross-platform Linux-to-Windows remote management and file synchronization service"
    )
    _exe_args_ = "service-run"

    def __init__(self, args: list[str]) -> None:
        if HAS_WIN32SERVICE:
            with contextlib.suppress(Exception):
                super().__init__(args)
            try:
                self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            except Exception:
                self.hWaitStop = None
        else:
            super().__init__(args)
            self.hWaitStop = None
        self._service: WindowsBridgeService | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def SvcStop(self) -> None:  # noqa: N802
        if HAS_WIN32SERVICE:
            with contextlib.suppress(Exception):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self.hWaitStop is not None:
                with contextlib.suppress(Exception):
                    win32event.SetEvent(self.hWaitStop)
        if self._service is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._service._stop_event.set)

    def SvcDoRun(self) -> None:  # noqa: N802
        if HAS_WIN32SERVICE:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
        self._run()

    def _run(self) -> None:
        exe_dir = Path(sys.executable).parent
        candidate_paths = [
            exe_dir / "bridge.toml",
            Path(r"C:\BridgeLocal\bridge.toml"),
            Path("bridge.toml"),
        ]
        cfg_path = None
        for p in candidate_paths:
            if p.exists():
                cfg_path = p
                break

        config = BridgeConfig.load(cfg_path)
        if cfg_path is not None and cfg_path.parent.exists():
            with contextlib.suppress(Exception):
                os.chdir(cfg_path.parent)

        self._service = WindowsBridgeService(config)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _main_task() -> None:
            assert self._service is not None
            await self._service.start()
            if HAS_WIN32SERVICE:
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            while not self._service._stop_event.is_set():
                if HAS_WIN32SERVICE and self.hWaitStop is not None:
                    rc = await asyncio.to_thread(
                        win32event.WaitForSingleObject, self.hWaitStop, 500
                    )
                    if rc == win32event.WAIT_OBJECT_0:
                        break
                else:
                    await asyncio.sleep(0.5)

            if HAS_WIN32SERVICE:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            await self._service.stop()
            if HAS_WIN32SERVICE:
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)

        try:
            self._loop.run_until_complete(_main_task())
        except Exception as exc:
            if HAS_WIN32SERVICE:
                servicemanager.LogErrorMsg(f"[FAIL] BridgeLocalAgent error: {exc}")
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
            raise
        finally:
            self._loop.close()


def run_scm_service() -> None:
    """Запуск службы под управлением Windows SCM (Service Control Manager)."""
    if not HAS_WIN32SERVICE:
        print("[FAIL] pywin32 не установлен. Служба SCM недоступна.")
        sys.exit(1)
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(BridgeLocalAgentWindowsService)
    servicemanager.StartServiceCtrlDispatcher()


def handle_service_command(args: list[str]) -> None:
    """Обработка команд управления системной службой Windows (win32serviceutil)."""
    if not HAS_WIN32SERVICE:
        print("[WARN] pywin32 не установлен. Установите: pip install pywin32")
        return
    argv = [f"{sys.argv[0]} service", *args]
    win32serviceutil.HandleCommandLine(BridgeLocalAgentWindowsService, argv=argv)


if __name__ == "__main__":
    main_standalone()
