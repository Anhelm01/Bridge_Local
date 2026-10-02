"""
bridge_agent_win.monitor — Интерактивный консольный монитор агента Windows.

Обеспечивает:
  - Живой мониторинг событий в реальном времени (получение заметок, передача файлов кармана,
    дублирование удаленного выполнения PowerShell с кодами выхода).
  - Интерактивную командную строку оператора прямо в работающей консоли (status, notes, pocket,
    reset, cls, exit).
  - Строгий контроль кодировки Windows-консоли (UTF-8 / CP65001) без кракозябр.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import os
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bridge_agent_win.service import WindowsBridgeService
    from bridge_core.config import BridgeConfig


def ensure_windows_console_encoding() -> None:
    """
    Принудительная настройка вывода UTF-8 для консоли Windows (chcp 65001).
    Предотвращает искажение кириллических символов и заметок.
    """
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            os.system("chcp 65001 >nul")
        for stream in (sys.stdout, sys.stderr):
            with contextlib.suppress(Exception):
                if hasattr(stream, "reconfigure"):
                    stream.reconfigure(encoding="utf-8", errors="replace")


def format_bytes(num_bytes: int) -> str:
    """Форматирование размера в человекочитаемый вид (Б, КБ, МБ, ГБ)."""
    if num_bytes < 1024:
        return f"{num_bytes} Б"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} КБ"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} МБ"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} ГБ"


class AgentConsoleMonitor:
    """
    Консольный интерактивный монитор для агента Windows.

    Отображает структурированные события (записки, файлы, команды) и
    обрабатывает локальные команды оператора.
    """

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._print_lock = threading.Lock()
        self._last_client_ping: dict[str, float] = {}
        self._stop_event = threading.Event()

    def print_line(self, line: str = "") -> None:
        """Потокобезопасный вывод строки в консоль."""
        with self._print_lock:
            try:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
            except Exception:
                pass

    def print_banner(self) -> None:
        """Отрисовка начального баннера монитора агента."""
        p_dir = str(self.config.get_pocket_dir())
        tok_state = "Включен (HMAC-SHA256)" if self.config.connection.psk_token else "Отключен"

        banner = [
            "==============================================================================",
            "           BRIDGE LOCAL — АГЕНТ WINDOWS (ИНТЕРАКТИВНЫЙ МОНИТОР)              ",
            "==============================================================================",
            f"  Слушать на:      {self.config.connection.host}:{self.config.connection.port}",
            f"  Каталог кармана: {p_dir}",
            f"  Безопасность:    {tok_state}",
            "------------------------------------------------------------------------------",
            "  Команды оператора (вводите в любое время):",
            "    status       — текущий статус, память, аптайм и активная сессия",
            "    notes        — последние полученные записки",
            "    pocket       — список файлов в Кармане",
            "    reset        — сброс рабочего каталога PowerShell (kill-session)",
            "    cls / clear  — очистить экран консоли",
            "    q / exit     — завершить сессию и остановить агент",
            "    help / ?     — справка по командам",
            "==============================================================================",
        ]
        with self._print_lock:
            for b in banner:
                sys.stdout.write(b + "\n")
            sys.stdout.flush()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.print_line(f"[{now_str}] [AGENT] Сервис запущен и ожидает запросов от Linux...\n")

    def on_event(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Обработка событий от WindowsBridgeService и вывод в консоль.
        """
        now = datetime.datetime.now().strftime("%H:%M:%S")

        if event_type == "note_received":
            src = data.get("source_node") or data.get("client_ip") or "Linux"
            text = data.get("text", "").strip()
            self.print_line(f"[{now}] [NOTE] Записка от {src}:")
            # Отступ для содержимого записки
            for line in text.splitlines():
                self.print_line(f"         \"{line}\"")
            self.print_line()

        elif event_type == "file_received":
            path = data.get("path", "")
            bytes_cnt = data.get("bytes", 0)
            client_ip = data.get("client_ip", "")
            size_str = format_bytes(bytes_cnt)
            self.print_line(
                f"[{now}] [POCKET] [ВХОДЯЩИЙ] Файл: \"{path}\" ({size_str}) "
                f"от {client_ip} ──► Сохранен [OK]"
            )

        elif event_type == "file_requested":
            path = data.get("path", "")
            total_size = data.get("total_size", 0)
            client_ip = data.get("client_ip", "")
            size_str = format_bytes(total_size)
            self.print_line(
                f"[{now}] [POCKET] [ИСХОДЯЩИЙ] Файл: \"{path}\" ({size_str}) "
                f"передан {client_ip} [OK]"
            )

        elif event_type == "exec_completed":
            cmd = data.get("command", "")
            exit_code = data.get("exit_code", 0)
            stdout = data.get("stdout", "").strip()
            stderr = data.get("stderr", "").strip()
            duration_ms = data.get("duration_ms", 0)
            working_dir = data.get("working_dir") or "По умолчанию"
            client_ip = data.get("client_ip", "")

            status_tag = "[OK]" if exit_code == 0 else f"[FAIL: {exit_code}]"
            self.print_line(f"[{now}] [EXEC] Команда от Linux ({client_ip}) {status_tag}:")
            self.print_line(f"         PS {working_dir}> {cmd}")

            if stdout:
                stdout_lines = stdout.splitlines()
                self.print_line("         --> Вывод:")
                # Ограничиваем вывод максимум 25 строками чтобы не забить терминал
                max_lines = 25
                for line in stdout_lines[:max_lines]:
                    self.print_line(f"             {line}")
                if len(stdout_lines) > max_lines:
                    self.print_line(f"             ... [еще {len(stdout_lines) - max_lines} строк]")

            if stderr:
                stderr_lines = stderr.splitlines()
                self.print_line("         --> Ошибка (stderr):")
                for line in stderr_lines[:15]:
                    self.print_line(f"             {line}")

            self.print_line(f"         --> Завершено [Код: {exit_code}] ({duration_ms} мс)\n")

        elif event_type == "client_ping":
            client_ip = data.get("client_ip", "unknown")
            last = self._last_client_ping.get(client_ip, 0)
            # Логируем пинг не чаще чем раз в 5 минут от одного клиента
            if time.time() - last > 300:
                self._last_client_ping[client_ip] = time.time()
                src = data.get("source_node", client_ip)
                self.print_line(
                    f"[{now}] [CLIENT] Связь с узлом {src} ({client_ip}) активна [Heartbeat OK]"
                )

    async def handle_command(self, cmd_line: str, service: WindowsBridgeService) -> None:
        """Обработка команд, введенных оператором в консоли Windows."""
        cmd = cmd_line.strip().lower()
        if not cmd:
            return

        now = datetime.datetime.now().strftime("%H:%M:%S")

        if cmd in ("q", "quit", "exit"):
            self.print_line(f"[{now}] [AGENT] Остановка сервиса по команде оператора...")
            service._stop_event.set()

        elif cmd == "status":
            uptime_sec = int(time.time() - service.start_time)
            h = uptime_sec // 3600
            m = (uptime_sec % 3600) // 60
            s = uptime_sec % 60
            uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

            cwd = service.executor.current_working_dir or "(Каталог запуска)"
            manifest = service.pocket_manager.scan_manifest()

            self.print_line(f"\n--- [СТАТУС АГЕНТА {now}] ---")
            self.print_line(f"  Аптайм процесса:      {uptime_str}")
            self.print_line(f"  Порт прослушивания:   {service.config.connection.port}")
            self.print_line(f"  Текущий CWD PowerShell: {cwd}")
            pock_sz = format_bytes(manifest.total_size_bytes)
            self.print_line(f"  Файлов в Кармане:     {manifest.file_count} ({pock_sz})")
            self.print_line(f"  Каталог логов:        {service.audit_logger.logs_dir}")
            self.print_line("-----------------------------\n")

        elif cmd == "notes":
            history = await service.notes_manager.get_history()
            self.print_line("\n--- [ПОСЛЕДНИЕ ЗАМЕТКИ] ---")
            if not history.notes:
                self.print_line("  (заметок пока нет)")
            else:
                for n in history.notes[-5:]:
                    author = (
                        n.author_os.value if hasattr(n.author_os, "value") else str(n.author_os)
                    )
                    dt = str(n.timestamp)[:19]
                    status_val = n.status.value if hasattr(n.status, "value") else str(n.status)
                    read_str = "Прочитана" if status_val == "read" else "Новая"
                    self.print_line(f"  [{dt}] {author} ({read_str}):")
                    self.print_line(f"    \"{n.text}\"")
            self.print_line("---------------------------\n")

        elif cmd == "pocket":
            manifest = service.pocket_manager.scan_manifest()
            self.print_line(f"\n--- [ФАЙЛЫ В КАРМАНЕ: {manifest.file_count}] ---")
            if not manifest.files:
                self.print_line("  (карман пуст)")
            else:
                for f in manifest.files[:20]:
                    sz = format_bytes(f.size_bytes)
                    self.print_line(f"  • {f.path} ({sz})")
                if len(manifest.files) > 20:
                    self.print_line(f"  ... и еще {len(manifest.files) - 20} файлов")
            self.print_line("---------------------------------\n")

        elif cmd in ("reset", "kill-session"):
            service.executor.current_working_dir = None
            self.print_line(f"[{now}] [AGENT] Рабочая директория PowerShell сброшена к исходной.")

        elif cmd in ("cls", "clear"):
            if sys.platform == "win32":
                os.system("cls")
            else:
                os.system("clear")
            self.print_banner()

        elif cmd in ("help", "?"):
            self.print_line("\nДоступные команды консоли:")
            self.print_line("  status       — вывод текущих метрик и статуса агента")
            self.print_line("  notes        — список последних 5 заметок")
            self.print_line("  pocket       — просмотр файлов в Кармане")
            self.print_line("  reset        — сброс рабочего каталога PowerShell (kill-session)")
            self.print_line("  cls / clear  — очистить экран")
            self.print_line("  q / exit     — остановить агент и выйти")
            self.print_line("  help / ?     — эта справка\n")

        else:
            self.print_line(
                f"[{now}] [WARN] Неизвестная команда '{cmd}'. Введите 'help' для справки."
            )

    def start_interactive_loop(self, service: WindowsBridgeService) -> threading.Thread | None:
        """
        Запускает фоновый поток для неблокирующего чтения ввода оператора из stdin.
        """
        # Если stdin не подключен к интерактивному терминалу (например, при тестах или SCM), выходим
        if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            return None

        loop = asyncio.get_running_loop()

        def _stdin_reader() -> None:
            while not self._stop_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    line_clean = line.strip()
                    if line_clean:
                        loop.call_soon_threadsafe(
                            asyncio.create_task,
                            self.handle_command(line_clean, service),
                        )
                except Exception:
                    break

        t = threading.Thread(target=_stdin_reader, daemon=True, name="ConsoleMonitorStdin")
        t.start()
        return t

    def stop(self) -> None:
        """Остановка монитора."""
        self._stop_event.set()
