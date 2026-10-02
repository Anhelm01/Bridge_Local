"""
bridge_agent_win.tray — Windows System Tray интеграция для Bridge Agent (bridge-agent tray).

Предоставляет:
  - Иконку в области уведомлений Windows (System Tray).
  - Всплывающее контекстное меню по правому клику мыши:
      * Статус узла и порта (ONLINE / STOPPED).
      * Состояние кармана (количество файлов и суммарный размер).
      * Быстрое открытие папки кармана в Проводнике (Explorer).
      * Открытие каталога логов и просмотр заметок.
      * Управление службой (Start / Stop / Restart Service) или standalone агентом.
      * Копирование адреса подключения (IP:Port) в буфер обмена.
      * Выход из трея.
  - Реакцию на двойной / одинарный левый клик — открытие папки кармана.
  - Фоновый опрос состояния службы и содержимого кармана с обновлением тултипа.
  - Корректную обработку перезапуска Проводника (WM_TASKBARCREATED).
"""

from __future__ import annotations

import contextlib
import logging
import os
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Автоматическое добавление каталога src/ в sys.path
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from bridge_agent_win.cli import get_local_ip_addresses  # noqa: E402
from bridge_core.config import BridgeConfig  # noqa: E402

logger = logging.getLogger(__name__)

win32gui: Any = None
win32con: Any = None
win32clipboard: Any = None
HAS_WIN32GUI = False
try:
    import win32clipboard as _win32clipboard
    import win32con as _win32con
    import win32gui as _win32gui

    win32clipboard = _win32clipboard
    win32con = _win32con
    win32gui = _win32gui
    HAS_WIN32GUI = True
except ImportError:
    pass

win32service: Any = None
win32serviceutil: Any = None
HAS_WIN32SERVICE = False
try:
    import win32service as _win32service
    import win32serviceutil as _win32serviceutil

    win32service = _win32service
    win32serviceutil = _win32serviceutil
    HAS_WIN32SERVICE = True
except ImportError:
    pass


# Идентификаторы команд контекстного меню
IDM_STATUS_HEADER = 1001
IDM_POCKET_INFO = 1002
IDM_OPEN_POCKET = 1003
IDM_OPEN_LOGS = 1004
IDM_OPEN_NOTES = 1005
IDM_COPY_ADDRESS = 1006
IDM_START_SERVICE = 1007
IDM_STOP_SERVICE = 1008
IDM_RESTART_SERVICE = 1009
IDM_START_AGENT = 1010
IDM_STOP_AGENT = 1011
IDM_DROP_CLIPBOARD = 1012
IDM_EXIT_TRAY = 1020


@dataclass
class TrayAgentStatus:
    """Структура с текущим срезом состояния Bridge Agent."""

    is_service_running: bool = False
    is_port_listening: bool = False
    is_online: bool = False
    file_count: int = 0
    total_size_bytes: int = 0
    host: str = "127.0.0.1"
    port: int = 9732
    pocket_dir: Path = Path("pocket")
    status_summary: str = "STOPPED"


def check_port_listening(host: str, port: int, timeout_sec: float = 0.5) -> bool:
    """Проверяет доступность TCP-порта локального агента."""
    target_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with socket.create_connection((target_host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def check_windows_service_status(service_name: str = "BridgeLocalAgent") -> int | None:
    """Возвращает код состояния службы Windows SCM или None при недоступности."""
    if not HAS_WIN32SERVICE:
        return None
    try:
        status = win32serviceutil.QueryServiceStatus(service_name)
        return int(status[1])
    except Exception:
        return None


def start_windows_service(service_name: str = "BridgeLocalAgent") -> bool:
    """Запускает системную службу Windows SCM."""
    if HAS_WIN32SERVICE:
        try:
            win32serviceutil.StartService(service_name)
            return True
        except Exception as e:
            logger.warning("[TRAY] win32serviceutil.StartService failed: %s, fallback to sc.exe", e)
    try:
        res = subprocess.run(
            ["sc.exe", "start", service_name],
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except Exception as e:
        logger.error("[TRAY] sc.exe start failed: %s", e)
        return False


def stop_windows_service(service_name: str = "BridgeLocalAgent") -> bool:
    """Останавливает системную службу Windows SCM."""
    if HAS_WIN32SERVICE:
        try:
            win32serviceutil.StopService(service_name)
            return True
        except Exception as e:
            logger.warning("[TRAY] win32serviceutil.StopService failed: %s, fallback to sc.exe", e)
    try:
        res = subprocess.run(
            ["sc.exe", "stop", service_name],
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except Exception as e:
        logger.error("[TRAY] sc.exe stop failed: %s", e)
        return False


def open_directory_in_explorer(path: Path) -> bool:
    """Открывает указанный каталог в Проводнике Windows (Explorer)."""
    p = path.resolve()
    p.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(p))
            return True
        else:
            subprocess.Popen(["xdg-open", str(p)])
            return True
    except Exception as e:
        logger.error("[TRAY] Ошибка открытия каталога %s: %s", p, e)
        return False


def copy_text_to_clipboard(text: str) -> bool:
    """Копирует текст в буфер обмена Windows."""
    if sys.platform == "win32" and HAS_WIN32GUI:
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            logger.info("[TRAY] Скопировано в буфер обмена: %s", text)
            return True
        except Exception as e:
            logger.warning("[TRAY] Ошибка записи в буфер обмена: %s", e)
            return False
    return False


def scan_pocket_statistics(pocket_dir: Path) -> tuple[int, int]:
    """
    Возвращает (file_count, total_size_bytes) для пользовательских файлов в кармане.
    Исключает внутренние каталоги .notes, logs и временные файлы .part.
    """
    if not pocket_dir.exists():
        return 0, 0

    count = 0
    total_size = 0
    try:
        for root, _dirs, files in os.walk(pocket_dir):
            rel = os.path.relpath(root, pocket_dir)
            if rel != ".":
                first_part = rel.replace("\\", "/").split("/")[0]
                if first_part in (".notes", "logs", ".git"):
                    continue
            for fn in files:
                if fn.startswith(".") or fn.endswith(".part"):
                    continue
                p = Path(root) / fn
                try:
                    total_size += p.stat().st_size
                    count += 1
                except OSError:
                    pass
    except Exception as e:
        logger.debug("[TRAY] Ошибка сканирования кармана %s: %s", pocket_dir, e)

    return count, total_size


class BridgeTrayIcon:
    """
    Управление иконкой Bridge Local в системном трее Windows.

    Обеспечивает визуальный мониторинг состояния, всплывающее меню и запуск/остановку.
    """

    WM_TRAY_CALLBACK = 0x8000 + 20  # WM_USER + 20

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self.config = config or BridgeConfig.load()
        self.pocket_dir = self.config.get_pocket_dir()
        self.host = self.config.connection.host
        self.port = self.config.connection.port

        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._agent_process: subprocess.Popen[Any] | None = None

        self.hwnd: int = 0
        self.hicon: int = 0
        self.wm_taskbar_created: int = 0
        self.current_status = TrayAgentStatus(
            host=self.host,
            port=self.port,
            pocket_dir=self.pocket_dir,
        )

    def get_status(self) -> TrayAgentStatus:
        """Собирает и возвращает свежий срез состояния службы и кармана."""
        svc_state = check_windows_service_status("BridgeLocalAgent")
        svc_running = (
            svc_state == win32service.SERVICE_RUNNING
            if (HAS_WIN32SERVICE and svc_state is not None)
            else False
        )

        port_listening = check_port_listening(self.host, self.port)
        is_online = svc_running or port_listening

        file_count, total_size = scan_pocket_statistics(self.pocket_dir)

        if svc_running:
            summary = "ONLINE (Service)"
        elif port_listening:
            summary = "ONLINE (Standalone)"
        else:
            summary = "STOPPED"

        status = TrayAgentStatus(
            is_service_running=svc_running,
            is_port_listening=port_listening,
            is_online=is_online,
            file_count=file_count,
            total_size_bytes=total_size,
            host=self.host,
            port=self.port,
            pocket_dir=self.pocket_dir,
            status_summary=summary,
        )
        self.current_status = status
        return status

    def open_pocket(self) -> bool:
        """Открывает каталог кармана в Explorer."""
        return open_directory_in_explorer(self.pocket_dir)

    def open_logs(self) -> bool:
        """Открывает каталог логов в Explorer."""
        logs_p = self.pocket_dir / self.config.pocket.logs_subdir
        return open_directory_in_explorer(logs_p)

    def open_notes(self) -> bool:
        """Открывает каталог заметок в Explorer."""
        notes_p = self.pocket_dir / ".notes"
        return open_directory_in_explorer(notes_p)

    def copy_connection_address(self) -> bool:
        """Копирует основной IP:Port в буфер обмена."""
        ips = get_local_ip_addresses()
        target_ip = ips[0] if ips else "127.0.0.1"
        addr_str = f"{target_ip}:{self.port}"
        return copy_text_to_clipboard(addr_str)

    def start_service(self) -> bool:
        """Запускает системную службу BridgeLocalAgent."""
        logger.info("[TRAY] Запуск системной службы...")
        ok = start_windows_service("BridgeLocalAgent")
        self.update_status()
        return ok

    def stop_service(self) -> bool:
        """Останавливает системную службу BridgeLocalAgent."""
        logger.info("[TRAY] Остановка системной службы...")
        ok = stop_windows_service("BridgeLocalAgent")
        self.update_status()
        return ok

    def restart_service(self) -> bool:
        """Перезапускает системную службу BridgeLocalAgent."""
        logger.info("[TRAY] Перезапуск системной службы...")
        stop_windows_service("BridgeLocalAgent")
        import time

        time.sleep(1.0)
        ok = start_windows_service("BridgeLocalAgent")
        self.update_status()
        return ok

    def start_standalone_agent(self) -> bool:
        """Запускает автономный фоновый процесс агента bridge-agent run."""
        if self._agent_process is not None and self._agent_process.poll() is None:
            logger.info("[TRAY] Автономный агент уже запущен (PID=%s)", self._agent_process.pid)
            return True

        cmd = [sys.executable, "-m", "bridge_agent_win.cli", "run"]
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        try:
            self._agent_process = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                cwd=str(self.pocket_dir.parent),
            )
            logger.info("[TRAY] Автономный агент запущен (PID=%s)", self._agent_process.pid)
            self.update_status()
            return True
        except Exception as e:
            logger.error("[TRAY] Ошибка запуска автономного агента: %s", e)
            return False

    def stop_standalone_agent(self) -> bool:
        """Останавливает автономный фоновый процесс агента."""
        if self._agent_process is not None and self._agent_process.poll() is None:
            logger.info("[TRAY] Остановка автономного агента (PID=%s)", self._agent_process.pid)
            with contextlib.suppress(Exception):
                self._agent_process.terminate()
            self._agent_process = None
            self.update_status()
            return True
        return False

    def update_status(self) -> None:
        """Обновляет состояние и тултип иконки в системном трее."""
        status = self.get_status()
        if not HAS_WIN32GUI or not self.hwnd:
            return

        size_kb = (status.total_size_bytes + 1023) // 1024
        tip = (
            f"Bridge Local: {status.status_summary}\n"
            f"Port: {status.port} | Pocket: {status.file_count} files ({size_kb} KB)"
        )[:127]

        nid = (
            self.hwnd,
            0,
            win32gui.NIF_TIP,
            self.WM_TRAY_CALLBACK,
            self.hicon,
            tip,
        )
        with contextlib.suppress(Exception):
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)

    # -----------------------------------------------------------------------
    # Внутренняя реализация Win32 GUI
    # -----------------------------------------------------------------------

    def _init_icon(self) -> int:
        """Загружает иконку для трея из shell32.dll или системного ресурса."""
        if not HAS_WIN32GUI:
            return 0
        # Попытка извлечь значок папки/моста из shell32.dll (индекс 46)
        try:
            icons = win32gui.ExtractIconEx("shell32.dll", 46)
            if icons and len(icons) > 1 and icons[1]:
                return int(icons[1][0])
        except Exception:
            pass

        try:
            return int(win32gui.LoadIcon(0, win32con.IDI_APPLICATION))
        except Exception:
            return 0

    def _create_window(self) -> None:
        """Создает невидимое окно для получения оконных сообщений трея."""
        assert HAS_WIN32GUI, "pywin32 требуется для работы Win32 окон"
        class_name = f"BridgeLocalTrayClass_{os.getpid()}"
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = class_name
        wc.lpfnWndProc = self._wnd_proc
        class_atom = win32gui.RegisterClass(wc)

        self.hwnd = win32gui.CreateWindow(
            class_atom,
            "Bridge Local Tray Window",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            wc.hInstance,
            None,
        )
        win32gui.UpdateWindow(self.hwnd)
        self.wm_taskbar_created = win32gui.RegisterWindowMessage("TaskbarCreated")

    def _add_tray_icon(self) -> None:
        """Регистрирует иконку в области уведомлений Windows."""
        if not HAS_WIN32GUI or not self.hwnd:
            return
        if not self.hicon:
            self.hicon = self._init_icon()

        tip = f"Bridge Local: {self.current_status.status_summary}"[:127]
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        nid = (self.hwnd, 0, flags, self.WM_TRAY_CALLBACK, self.hicon, tip)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
            logger.info("[TRAY] Иконка успешно добавлена в System Tray Windows.")
        except Exception as e:
            logger.error("[TRAY] Ошибка регистрации иконки в Shell_NotifyIcon: %s", e)

    def _remove_tray_icon(self) -> None:
        """Удаляет иконку из трея."""
        if not HAS_WIN32GUI or not self.hwnd:
            return
        nid = (self.hwnd, 0)
        with contextlib.suppress(Exception):
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        logger.info("[TRAY] Иконка удалена из System Tray.")

    def _show_menu(self) -> None:
        """Отображает всплывающее контекстное меню по правому клику."""
        if not HAS_WIN32GUI or not self.hwnd:
            return

        status = self.get_status()
        menu = win32gui.CreatePopupMenu()

        # 1. Заголовок со статусом (некликабельный пункт)
        header_text = f"Bridge Local: {status.status_summary} (Port {status.port})"
        win32gui.AppendMenu(
            menu,
            win32con.MF_STRING | win32con.MF_GRAYED,
            IDM_STATUS_HEADER,
            header_text,
        )

        # 2. Информация о кармане
        size_kb = (status.total_size_bytes + 1023) // 1024
        pocket_text = f"Карман: {status.file_count} файлов ({size_kb} KB)"
        win32gui.AppendMenu(menu, win32con.MF_STRING, IDM_POCKET_INFO, pocket_text)

        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")

        # 3. Действия с каталогами и буфером
        win32gui.AppendMenu(menu, win32con.MF_STRING, IDM_OPEN_POCKET, "Открыть Карман в Explorer")
        win32gui.AppendMenu(
            menu,
            win32con.MF_STRING,
            IDM_DROP_CLIPBOARD,
            "Вставить из буфера в Карман (Drop Clipboard)",
        )
        win32gui.AppendMenu(menu, win32con.MF_STRING, IDM_OPEN_LOGS, "Открыть журнал логов")
        win32gui.AppendMenu(menu, win32con.MF_STRING, IDM_OPEN_NOTES, "Открыть записки (.notes)")
        win32gui.AppendMenu(
            menu, win32con.MF_STRING, IDM_COPY_ADDRESS, "Копировать адрес узла (IP:Port)"
        )

        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")

        # 4. Управление службой / процессом
        if status.is_service_running:
            win32gui.AppendMenu(
                menu, win32con.MF_STRING, IDM_STOP_SERVICE, "Остановить службу (Stop Service)"
            )
            win32gui.AppendMenu(
                menu,
                win32con.MF_STRING,
                IDM_RESTART_SERVICE,
                "Перезапустить службу (Restart Service)",
            )
        elif status.is_port_listening and self._agent_process:
            win32gui.AppendMenu(
                menu, win32con.MF_STRING, IDM_STOP_AGENT, "Остановить автономный агент"
            )
        else:
            win32gui.AppendMenu(
                menu, win32con.MF_STRING, IDM_START_SERVICE, "Запустить службу (Start Service)"
            )
            win32gui.AppendMenu(
                menu, win32con.MF_STRING, IDM_START_AGENT, "Запустить в фоне (Standalone)"
            )

        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")

        # 5. Выход
        win32gui.AppendMenu(menu, win32con.MF_STRING, IDM_EXIT_TRAY, "Выход (Закрыть трей)")

        # Корректное отображение контекстного меню Win32 (MSDN KB135788)
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
            pos[0],
            pos[1],
            0,
            self.hwnd,
            None,
        )
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _dispatch_command(self, cmd_id: int) -> None:
        """Маршрутизация выбора пункта контекстного меню."""
        if cmd_id in (IDM_POCKET_INFO, IDM_OPEN_POCKET):
            self.open_pocket()
        elif cmd_id == IDM_DROP_CLIPBOARD:
            from bridge_agent_win.context_menu import drop_clipboard_to_pocket

            drop_clipboard_to_pocket(show_alert=True)
        elif cmd_id == IDM_OPEN_LOGS:
            self.open_logs()
        elif cmd_id == IDM_OPEN_NOTES:
            self.open_notes()
        elif cmd_id == IDM_COPY_ADDRESS:
            self.copy_connection_address()
        elif cmd_id == IDM_START_SERVICE:
            self.start_service()
        elif cmd_id == IDM_STOP_SERVICE:
            self.stop_service()
        elif cmd_id == IDM_RESTART_SERVICE:
            self.restart_service()
        elif cmd_id == IDM_START_AGENT:
            self.start_standalone_agent()
        elif cmd_id == IDM_STOP_AGENT:
            self.stop_standalone_agent()
        elif cmd_id == IDM_EXIT_TRAY:
            self.stop()

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Оконная процедура Win32."""
        if msg == self.wm_taskbar_created:
            # Explorer перезапустился — пересоздаем иконку
            self._add_tray_icon()
            return 0

        if msg == self.WM_TRAY_CALLBACK:
            if lparam in (win32con.WM_RBUTTONUP, win32con.WM_CONTEXTMENU):
                self._show_menu()
                return 0
            if lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
                self.open_pocket()
                return 0

        elif msg == win32con.WM_COMMAND:
            cmd_id = win32gui.LOWORD(wparam)
            self._dispatch_command(cmd_id)
            return 0

        elif msg == win32con.WM_DESTROY:
            self._remove_tray_icon()
            win32gui.PostQuitMessage(0)
            return 0

        return int(win32gui.DefWindowProc(hwnd, msg, wparam, lparam))

    def _status_poll_loop(self) -> None:
        """Фоновый поток периодического обновления статуса."""
        while not self._stop_event.is_set():
            with contextlib.suppress(Exception):
                self.update_status()
            self._stop_event.wait(timeout=2.5)

    def run(self) -> None:
        """Запускает оконный цикл трея (блокирующий вызов)."""
        if not HAS_WIN32GUI:
            print("[WARN] pywin32 GUI модули недоступны на этой платформе.")
            return

        self._create_window()
        self.get_status()
        self._add_tray_icon()

        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._status_poll_loop,
            daemon=True,
            name="TrayStatusPollThread",
        )
        self._poll_thread.start()

        print("[OK] Bridge Local System Tray активен. Иконка добавлена в область уведомлений.")
        win32gui.PumpMessages()

    def stop(self) -> None:
        """Останавливает цикл трея и освобождает ресурсы."""
        self._stop_event.set()
        if self._agent_process is not None:
            self.stop_standalone_agent()
        if HAS_WIN32GUI and self.hwnd:
            self._remove_tray_icon()
            win32gui.DestroyWindow(self.hwnd)
            win32gui.PostQuitMessage(0)
            self.hwnd = 0


def main() -> None:
    """Точка входа для запуска Bridge Agent Tray."""
    tray = BridgeTrayIcon()
    try:
        tray.run()
    except (KeyboardInterrupt, SystemExit):
        tray.stop()


if __name__ == "__main__":
    main()
