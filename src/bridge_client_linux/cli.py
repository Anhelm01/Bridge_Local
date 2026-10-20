"""
bridge_client_linux.cli — Консольный интерфейс Bridge Local (bridge-cli).

Поддерживает два режима работы:
  1. Человеческий (Human Ergonomics): цветной вывод Rich, таблицы, TUI, Neofetch splash.
  2. ИИ-агент (AI Operator / agy_cli): строго детерминированный JSON (--json),
     нулевой ANSI-мусор, отсутствие блокировок stdin, стандартизированные exit-коды (0..5).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bridge_client_linux.client import BridgeClient
from bridge_client_linux.clipboard import copy_text_to_clipboard, get_clipboard_content
from bridge_client_linux.exceptions import (
    BridgeClientError,
    format_error_payload,
)
from bridge_client_linux.exit_codes import ExitCode
from bridge_client_linux.tui.app import run_interactive_tui
from bridge_client_linux.tui.screens import format_bytes
from bridge_client_linux.tui.theme import OFFICIAL_THEME
from bridge_core.config import BridgeConfig
from bridge_core.models import NodeOS, PocketClearResult
from bridge_core.process_killer import is_pid_running as _is_pid_alive
from bridge_core.process_killer import kill_process_tree
from bridge_core.service import BridgeService
from bridge_core.transport import check_port_listening as _check_port_listening

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="bridge-cli",
    help="Bridge Local: Cross-platform Linux-to-Windows communication & file sync backbone",
    no_args_is_help=False,
)

pocket_app = typer.Typer(
    name="pocket",
    help="Управление общим хранилищем «Карман» (Pocket Storage)",
)
note_app = typer.Typer(
    name="note",
    help="Быстрый обмен заметками и ссылками между экранами (Notes Engine)",
)
config_app = typer.Typer(
    name="config",
    help="Просмотр и управление конфигурацией bridge.toml",
)
service_app = typer.Typer(
    name="service",
    help="Управление фоновой службой узла (Bridge Service Daemon / systemd)",
)

app.add_typer(pocket_app, name="pocket")
app.add_typer(note_app, name="note")
app.add_typer(config_app, name="config")
app.add_typer(service_app, name="service")

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False if sys.platform == "win32" else None)


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Синхронный запуск асинхронной корутины."""
    return asyncio.run(coro)


def _output_json(data: Any, exit_code: int = ExitCode.SUCCESS) -> None:
    """Выводит чистый JSON без ANSI-символов в stdout и завершает процесс."""
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    sys.stdout.write(serialized + "\n")
    sys.stdout.flush()
    if exit_code != ExitCode.SUCCESS:
        raise typer.Exit(code=exit_code)


def _handle_error(e: Exception, as_json: bool = False) -> None:
    """Обрабатывает исключения с возвратом детерминированных кодов завершения."""
    code, payload = format_error_payload(e)

    if as_json:
        _output_json(payload, exit_code=code)
    else:
        console.print(f"[bold red][ERROR {code}][/] {e}")
        raise typer.Exit(code=code)


def _get_client(
    config_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    token: str | None = None,
    node: str | None = None,
) -> BridgeClient:
    """Создаёт настроенный инстанс BridgeClient."""
    cfg = BridgeConfig.load(config_path)
    return BridgeClient(
        config=cfg,
        host=host,
        port=port,
        psk_token=token,
        target_node=node,
    )


# ---------------------------------------------------------------------------
# 1. Root & Status Commands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", "-j", help="Машиночитаемый JSON вывод для ИИ"),
    version: bool = typer.Option(False, "--version", "-v", help="Версия Bridge Local"),
) -> None:
    """Главная точка входа bridge-cli."""
    if version:
        ver_info = {"version": "0.3.0", "core": "bridge_core", "target": "Linux/Windows (Dual-Role Peer)"}
        if json_mode:
            _output_json(ver_info)
        else:
            console.print("[bold white]Bridge Local[/] v0.3.0 (Universal P2P Node / Dual-Role Peer)")
        raise typer.Exit()

    # Если команда не задана:
    if ctx.invoked_subcommand is None:
        if json_mode:
            _output_json({"status": "ready", "hint": "Use 'bridge-cli --help' for commands"})
            raise typer.Exit()
        if sys.stdin.isatty():
            # Запуск TUI в интерактивном терминале (Master Fullscreen Omnibar)
            run_interactive_tui(theme=OFFICIAL_THEME, initial_mode="MAIN")
            raise typer.Exit()
        else:
            console.print(ctx.get_help())
            raise typer.Exit()


@app.command("status")
def cmd_status(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен аутентификации"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя целевого узла"),
) -> None:
    """Проверка сводного статуса связи, метрик узла, кармана и заметок."""
    client = _get_client(config, host, port, token, node)

    async def _action() -> dict[str, Any]:
        async with client:
            return await client.get_system_status()

    try:
        data = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(data)
        return

    # Красивый вывод для оператора
    conn = data["connection"]
    remote = data["remote"]
    pock = data["pocket"]
    notes = data["notes"]

    table = Table(title="◈ BRIDGE LOCAL SYSTEM STATUS ◈", expand=True)
    table.add_column("Подсистема", style="bold white", width=22)
    table.add_column("Параметры", style="dim white")
    table.add_column("Состояние", style="bold green", justify="center")

    table.add_row(
        "Сеть & P2P Связь",
        f"Host: {data['node']['host']}:{data['node']['port']} · Ping: {conn['latency_ms']} ms",
        f"[bold green]{conn['status'].upper()}[/]",
    )
    table.add_row(
        f"Удалённый агент ({remote['os']})",
        (
            f"CPU: {remote['cpu_percent']}% · RAM: {remote['memory_used_mb']} MB"
            f" · Uptime: {remote['uptime_seconds']}s"
        ),
        f"[bold green]{remote['status'].upper()}[/]",
    )
    table.add_row(
        "Карман (Pocket)",
        (
            f"Локально: {pock['local_files']} ф. · Удалённо: {pock['remote_files']} ф."
            f" · Push: {pock['pending_push']}, Pull: {pock['pending_pull']}"
        ),
        "[bold green]SYNCED[/]" if pock["in_sync"] else "[bold yellow]DIFF[/]",
    )
    table.add_row(
        "Записки (Notes)",
        f"Всего: {notes['total']} · Непрочитанных: {notes['unread']}",
        "[bold green]OK[/]" if notes["unread"] == 0 else f"[bold yellow]{notes['unread']} NEW[/]",
    )

    console.print(table)


@app.command("ping")
def cmd_ping(
    count: int = typer.Option(1, "--count", "-n", min=1, max=10, help="Количество проб"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", help="Имя узла"),
) -> None:
    """Heartbeat-проверка доступности удаленного агента."""
    client = _get_client(config, host, port, token, node)

    async def _action() -> list[dict[str, Any]]:
        results = []
        async with client:
            for _ in range(count):
                pong, rtt = await client.ping()
                results.append({"latency_ms": rtt, "pong": pong.model_dump()})
                if count > 1:
                    await asyncio.sleep(0.5)
        return results

    try:
        data = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json({"pings": data, "target_node": client.target_node})
        return

    for item in data:
        rtt = item["latency_ms"]
        p = item["pong"]
        console.print(
            f"[bold green]PONG[/] from [bold {OFFICIAL_THEME.purple}]{client.target_node}[/] "
            f"({p['agent_os']}): rtt=[bold {OFFICIAL_THEME.blue}]{rtt}ms[/] "
            f"status=[bold {OFFICIAL_THEME.green}]{p['status']}[/] "
            f"cpu={p['cpu_percent']}% ram={p['memory_used_mb']}MB"
        )


# ---------------------------------------------------------------------------
# 2. Exec Command (PowerShell Remote Execution)
# ---------------------------------------------------------------------------


@app.command("exec")
def cmd_exec(
    command: str = typer.Argument(..., help="Команда PowerShell для выполнения"),
    timeout: int = typer.Option(30, "--timeout", "-T", help="Таймаут в секундах"),
    admin: bool = typer.Option(True, "--admin/--no-admin", help="Запуск с правами Администратора"),
    working_dir: str | None = typer.Option(None, "--dir", "-d", help="Рабочий каталог"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла-исполнителя"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Удалённый запуск команд PowerShell на узле Windows с детерминированным exit-кодом."""
    client = _get_client(config, host, port, token, node)

    async def _action() -> Any:
        async with client:
            return await client.exec(
                command=command,
                timeout_sec=timeout,
                run_as_admin=admin,
                working_dir=working_dir,
                target_node=node,
            )

    try:
        res = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        data = res.model_dump()
        exit_code = ExitCode.SUCCESS if res.exit_code == 0 else ExitCode.COMMAND_FAILED
        _output_json(data, exit_code=exit_code)
        return

    # Человеческий вывод
    if res.stdout:
        sys.stdout.write(res.stdout)
        if not res.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if res.stderr:
        sys.stderr.write(res.stderr)
        if not res.stderr.endswith("\n"):
            sys.stderr.write("\n")

    if res.exit_code != 0:
        raise typer.Exit(code=ExitCode.COMMAND_FAILED)


# ---------------------------------------------------------------------------
# 3. Pocket Storage Subcommands
# ---------------------------------------------------------------------------


@pocket_app.command("status")
def cmd_pocket_status(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", help="Имя узла"),
) -> None:
    """Статус синхронизации локального и удаленного кармана."""
    client = _get_client(config, host, port, token, node)

    async def _action() -> dict[str, Any]:
        async with client:
            return await client.pocket_status()

    try:
        stat = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(stat)
        return

    table = Table(title="◈ POCKET STORAGE STATUS ◈", expand=True)
    table.add_column("Параметр", style="bold white")
    table.add_column("Значение", style=f"bold {OFFICIAL_THEME.blue}")

    table.add_row("Локальный путь", stat["local_path"])
    table.add_row(
        "Файлов (Local / Remote)",
        f"{stat['local_files_count']} / {stat['remote_files_count']}",
    )
    table.add_row(
        "Размер (Local / Remote)",
        f"{stat['local_total_bytes']} B / {stat['remote_total_bytes']} B",
    )
    table.add_row(
        "Очередь PULL (скачать)",
        f"{len(stat['to_pull'])} файлов",
    )
    table.add_row(
        "Очередь PUSH (отправить)",
        f"{len(stat['to_push'])} файлов",
    )
    table.add_row(
        "Статус синхронизации",
        "[bold green]100% IN SYNC[/]" if stat["is_in_sync"] else "[bold yellow]NEEDS SYNC[/]",
    )

    console.print(table)


@pocket_app.command("sync")
def cmd_pocket_sync(
    direction: str = typer.Option(
        "both", "--direction", "-d", help="Направление: both | push | pull"
    ),
    watch: bool = typer.Option(
        False, "--watch", "-w", help="Режим непрерывного наблюдения и автосинхронизации"
    ),
    interval: float = typer.Option(
        2.5, "--interval", "-i", help="Интервал опроса в режиме --watch (секунды)"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", help="Имя узла"),
) -> None:
    """Двунаправленная или однонаправленная синхронизация файлов кармана."""
    client = _get_client(config, host, port, token, node)

    async def _action() -> Any:
        async with client:
            return await client.pocket_sync(direction=direction)

    if watch:
        _run_pocket_watch(client, json_mode=json_mode)
        return

    try:
        summary = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        from dataclasses import asdict

        payload = (
            asdict(summary) if hasattr(summary, "__dataclass_fields__") else summary.model_dump()
        )
        _output_json(payload)
        return

    console.print(
        f"[bold {OFFICIAL_THEME.green}][OK] Синхронизация завершена за {summary.duration_ms} мс[/]"
    )
    console.print(
        f"  Pulled: [bold {OFFICIAL_THEME.blue}]{len(summary.pulled)}[/] | "
        f"Pushed: [bold {OFFICIAL_THEME.amber}]{len(summary.pushed)}[/] | "
        f"Synced: [bold {OFFICIAL_THEME.green}]{len(summary.synced)}[/] | "
        f"Bytes: [dim]{summary.total_bytes_transferred}[/]"
    )
    if summary.errors:
        for err in summary.errors:
            console.print(f"  [bold red]Ошибка:[/] {err}")


def _run_pocket_watch(
    client: BridgeClient,
    json_mode: bool = False,
) -> None:
    """Реализация Real-Time двусторонней автосинхронизации кармана без холостого поллинга CPU."""
    from datetime import datetime

    from bridge_core.pocket import PocketWatcher

    async def _async_watch() -> None:
        async with client:
            if not json_mode:
                console.print(
                    f"[bold {OFFICIAL_THEME.blue}]◈ REAL-TIME EVENT-DRIVEN POCKET WATCH ◈[/]\n"
                    f"  Локальный карман: [cyan]{client.pocket_dir}[/]\n"
                    f"  Удалённый узел:   [cyan]{client.host}:{client.port}[/] (AEAD шифрование активно)\n"
                    f"  [dim]0.00% CPU в покое (системные события ядра), дебаунс и стабилизация 500 мс[/]\n"
                    f"  [dim]Для остановки нажмите Ctrl+C[/]\n"
                )

            # 1. Первоначальная двусторонняя сверка
            try:
                initial_summary = await client.pocket_sync(direction="both")
                if (initial_summary.pulled or initial_summary.pushed) and not json_mode:
                    now_str = datetime.now().strftime("%H:%M:%S")
                    console.print(
                        f"[{now_str}] [bold {OFFICIAL_THEME.green}][INITIAL-SYNC][/] "
                        f"Pulled: {len(initial_summary.pulled)}, Pushed: {len(initial_summary.pushed)}"
                    )
            except Exception:
                pass

            sync_lock = asyncio.Lock()

            # 2. Локальный watcher ядра (inotify)
            async def _on_local_change(paths: list[str]) -> None:
                async with sync_lock:
                    try:
                        summary = await client.pocket_sync(direction="push")
                        if summary.pushed:
                            now_str = datetime.now().strftime("%H:%M:%S")
                            if json_mode:
                                sys.stdout.write(
                                    json.dumps(
                                        {
                                            "event": "local_push",
                                            "files": summary.pushed,
                                            "time": now_str,
                                        },
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                )
                                sys.stdout.flush()
                            else:
                                console.print(
                                    f"[{now_str}] [bold {OFFICIAL_THEME.amber}]↑ PUSH (локально):[/] "
                                    f"[green]{', '.join(summary.pushed)}[/]"
                                )
                    except Exception as err:
                        logger.error("[WATCH-PUSH-ERROR] %s", err)

            watcher = PocketWatcher(
                pocket_dir=client.pocket_dir,
                on_change_callback=_on_local_change,
                debounce_sec=0.5,
            )
            watcher.start()

            # 3. Ожидание событий от ядра Windows (ReadDirectoryChangesW)
            last_event_id = 0
            try:
                while True:
                    try:
                        res = await client.pocket_wait_events(
                            last_event_id=last_event_id, timeout_sec=25.0
                        )
                        last_event_id = res.event_id
                        if res.has_changes and res.changed_files:
                            async with sync_lock:
                                summary = await client.pocket_sync(direction="pull")
                                if summary.pulled:
                                    now_str = datetime.now().strftime("%H:%M:%S")
                                    if json_mode:
                                        sys.stdout.write(
                                            json.dumps(
                                                {
                                                    "event": "remote_pull",
                                                    "files": summary.pulled,
                                                    "time": now_str,
                                                },
                                                ensure_ascii=False,
                                            )
                                            + "\n"
                                        )
                                        sys.stdout.flush()
                                    else:
                                        console.print(
                                            f"[{now_str}] [bold {OFFICIAL_THEME.blue}]↓ PULL (удалённо):[/] "
                                            f"[cyan]{', '.join(summary.pulled)}[/]"
                                        )
                    except TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break
                    except Exception:
                        await asyncio.sleep(2.0)
            finally:
                watcher.stop()

    try:
        _run(_async_watch())
    except KeyboardInterrupt:
        if not json_mode:
            console.print(
                f"\n[bold {OFFICIAL_THEME.amber}][WATCH] Наблюдение за карманом остановлено.[/]"
            )


@pocket_app.command("watch")
@app.command("watch")
def cmd_pocket_watch(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод событий в JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", help="Имя узла"),
) -> None:
    """Непрерывное двустороннее отслеживание кармана в реальном времени (0.00% CPU)."""
    client = _get_client(config, host, port, token, node)
    _run_pocket_watch(client, json_mode=json_mode)


@pocket_app.command("push")
def cmd_pocket_push(
    file_path: Path = typer.Argument(..., help="Путь к локальному файлу для загрузки"),
    target_path: str | None = typer.Option(
        None, "--target", "-t", help="Относительное имя файла в удаленном кармане"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Загрузка файла в удаленный карман."""
    client = _get_client(config, host, port, token)

    async def _action() -> Any:
        async with client:
            return await client.pocket_push_file(file_path, target_rel_path=target_path)

    try:
        res = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(res.model_dump())
        return

    console.print(
        f"[bold {OFFICIAL_THEME.green}][OK] Файл {file_path.name} успешно загружен в карман[/]"
    )


@pocket_app.command("pull")
def cmd_pocket_pull(
    remote_file: str = typer.Argument(..., help="Относительное имя файла в удаленном кармане"),
    dest: Path | None = typer.Option(None, "--dest", "-d", help="Локальный путь назначения"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Скачивание файла из удаленного кармана."""
    client = _get_client(config, host, port, token)

    async def _action() -> Path:
        async with client:
            return await client.pocket_pull_file(remote_file, dest_local_path=dest)

    try:
        saved_path = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json({"status": "downloaded", "path": str(saved_path)})
        return

    console.print(
        f"[bold {OFFICIAL_THEME.green}][OK] Файл {remote_file} успешно сохранён в {saved_path}[/]"
    )


@pocket_app.command("path")
def cmd_pocket_path(
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> None:
    """Выводит абсолютный путь к активному каталогу кармана."""
    cfg = BridgeConfig.load(config)
    p = cfg.get_pocket_dir()
    if json_mode:
        _output_json({"pocket_path": str(p), "exists": p.exists()})
        return
    console.print(str(p))


@pocket_app.command("drop")
def cmd_pocket_drop(
    files: list[Path] | None = typer.Argument(None, help="Пути к файлам для отправки в карман"),
    from_clipboard: bool = typer.Option(
        False, "--clipboard", "-B", help="Взять файлы, скриншот или текст из буфера обмена"
    ),
    target_dir: str | None = typer.Option(None, "--target-dir", "-d", help="Подкаталог в кармане"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="Токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла"),
) -> None:
    """Быстрая отправка файлов в удалённый карман (псевдоним для send)."""
    cmd_send(
        files=files,
        from_clipboard=from_clipboard,
        target_dir=target_dir,
        json_mode=json_mode,
        config=config,
        host=host,
        port=port,
        token=token,
        node=node,
    )


@pocket_app.command("clear")
def cmd_pocket_clear(
    local_only: bool = typer.Option(
        False, "--local", "-l", help="Очистить только локальный карман на Linux"
    ),
    remote_only: bool = typer.Option(
        False, "--remote", "-r", help="Очистить только удалённый карман на Windows"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Удалить файлы без запроса подтверждения"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="Токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла"),
) -> None:
    """Безопасная очистка кармана от файлов (сохраняет logs/ и .notes/)."""
    if local_only and remote_only:
        _handle_error(
            BridgeClientError("Флаги --local и --remote взаимоисключающие."),
            as_json=json_mode,
        )
        return

    if not force and not json_mode:
        targets_str = "локальный и удалённый карманы"
        if local_only:
            targets_str = "локальный карман (Linux)"
        elif remote_only:
            targets_str = "удалённый карман (Windows)"
        if not typer.confirm(f"Вы уверены, что хотите очистить {targets_str}?", default=False):
            console.print("[dim]Очистка отменена.[/]")
            return

    client = _get_client(config, host, port, token, node)
    deleted_local = 0
    freed_local = 0
    deleted_remote = 0
    freed_remote = 0

    # 1. Очистка локального кармана
    if not remote_only:
        try:
            deleted_local, freed_local = client.pocket_manager.clear_pocket()
        except Exception as e:
            _handle_error(BridgeClientError(f"Ошибка локальной очистки: {e}"), as_json=json_mode)
            return

    # 2. Очистка удалённого кармана
    if not local_only:

        async def _clear_remote() -> PocketClearResult:
            async with client:
                return await client.pocket_clear(target_node=node)

        try:
            rem_res = _run(_clear_remote())
            deleted_remote = rem_res.deleted_count
            freed_remote = rem_res.freed_bytes
        except Exception as e:
            _handle_error(e, as_json=json_mode)
            return

    total_deleted = deleted_local + deleted_remote
    total_freed = freed_local + freed_remote

    if json_mode:
        _output_json(
            {
                "status": "success",
                "deleted_local": deleted_local,
                "freed_bytes_local": freed_local,
                "deleted_remote": deleted_remote,
                "freed_bytes_remote": freed_remote,
                "total_deleted": total_deleted,
                "total_freed_bytes": total_freed,
            }
        )
        return

    console.print(f"[bold {OFFICIAL_THEME.green}][OK] Карман успешно очищен[/]")
    if not remote_only:
        console.print(
            f"  • Локально (Linux):   удалено [bold white]{deleted_local}[/] файлов ([dim]{freed_local} B[/])"
        )
    if not local_only:
        console.print(
            f"  • Удалённо (Windows): удалено [bold white]{deleted_remote}[/] файлов ([dim]{freed_remote} B[/])"
        )


@pocket_app.command("list")
def cmd_pocket_list(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Отображение содержимого локального кармана."""
    cfg = BridgeConfig.load(config)
    pocket_dir = cfg.get_pocket_dir()
    if not pocket_dir.exists():
        if json_mode:
            _output_json({"pocket_path": str(pocket_dir), "files": [], "count": 0})
            return
        console.print(f"[bold yellow]Каталог кармана не существует: {pocket_dir}[/]")
        return
    items = []
    for f in pocket_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(pocket_dir)
            size = f.stat().st_size
            items.append({"file": str(rel), "size_bytes": size})
    if json_mode:
        _output_json({"pocket_path": str(pocket_dir), "files": items, "count": len(items)})
        return
    console.print(f"[bold cyan]Содержимое кармана ({pocket_dir}):[/]")
    if not items:
        console.print("  [dim](карман пуст)[/]")
    else:
        for it in items:
            console.print(f"  • [bold white]{it['file']}[/] [dim]({it['size_bytes']} байт)[/]")


# ---------------------------------------------------------------------------
# 3.4 Remote File Browsing & Searching (fs.list / fs.find)
# ---------------------------------------------------------------------------


@app.command("ls")
def cmd_ls(
    path: str | None = typer.Argument(
        None, help="Удалённый путь для просмотра (или None для текущего каталога)"
    ),
    pocket: bool = typer.Option(False, "--pocket", "-p", help="Просмотреть удалённый карман"),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Рекурсивный обход подкаталогов"
    ),
    limit: int = typer.Option(300, "--limit", "-l", help="Максимальное количество записей"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла"),
) -> None:
    """Удалённый просмотр содержимого папки на целевом узле Windows (fs.list)."""
    client = _get_client(config, host, port, token, node)

    async def _do_ls() -> Any:
        async with client:
            return await client.fs_list(
                path=path,
                pocket_only=pocket,
                recursive=recursive,
                max_items=limit,
                target_node=node,
            )

    try:
        res = _run(_do_ls())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(
            {
                "target_path": res.target_path,
                "total_entries": res.total_entries,
                "entries": [e.model_dump() for e in res.entries],
            }
        )
        return

    console.print(
        f"\n[bold {OFFICIAL_THEME.blue}]📁 Каталог на удалённом узле:[/] [bold white]{res.target_path}[/] "
        f"[dim]({res.total_entries} элементов)[/]\n"
    )

    if not res.entries:
        console.print("[dim]  (каталог пуст)[/]\n")
        return

    table = Table(
        box=None,
        border_style=OFFICIAL_THEME.secondary,
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("Тип", style="bold", width=6)
    table.add_column("Имя", style="bold white", min_width=24)
    table.add_column("Размер", justify="right", min_width=12)
    table.add_column("Изменён", style="dim", min_width=20)

    for entry in res.entries:
        if entry.is_dir:
            type_tag = "[bold cyan]DIR[/]"
            name_str = f"[bold cyan]{entry.name}/[/]"
            size_str = "[dim]--[/]"
        else:
            type_tag = "[dim]FILE[/]"
            name_str = f"[white]{entry.name}[/]"
            size_str = format_bytes(entry.size_bytes)

        m_str = entry.modified_iso[:19].replace("T", " ") if entry.modified_iso else "--"
        table.add_row(type_tag, name_str, size_str, m_str)

    console.print(table)
    console.print()


@app.command("find")
def cmd_find(
    pattern: str = typer.Argument(
        ..., help="Маска поиска или подстрока (например *.txt, *.log, report)"
    ),
    directory: str | None = typer.Option(None, "--dir", "-d", help="Корневой каталог поиска"),
    pocket: bool = typer.Option(False, "--pocket", "-p", help="Искать только в удалённом кармане"),
    fetch: bool = typer.Option(
        False, "--fetch", "-f", help="Скачать найденные файлы в локальный карман"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Максимальное количество результатов"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла"),
) -> None:
    """Удалённый поиск файлов на узле Windows по маске или подстроке (fs.find)."""
    client = _get_client(config, host, port, token, node)

    async def _do_find() -> Any:
        async with client:
            return await client.fs_find(
                pattern=pattern,
                directory=directory,
                pocket_only=pocket,
                max_results=limit,
                target_node=node,
            )

    try:
        res = _run(_do_find())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    fetched_files: list[str] = []
    if fetch and res.entries:

        async def _do_fetch_all() -> list[str]:
            async with client:
                downloaded = []
                for entry in res.entries:
                    if entry.is_dir:
                        continue
                    rel_p = Path(entry.name).name
                    try:
                        # Если файл вне кармана, копируем его в карман на Windows перед загрузкой
                        if not pocket:
                            escaped_src = entry.path.replace("'", "''")
                            copy_cmd = f"Copy-Item -LiteralPath '{escaped_src}' -Destination '.\\pocket\\{rel_p}' -Force"
                            await client.exec(copy_cmd, timeout_sec=15)
                        pulled = await client.pocket_pull_file(rel_p)
                        downloaded.append(str(pulled))
                    except Exception as exc:
                        if not json_mode:
                            console.print(f"[yellow][WARN] Сбой скачивания {entry.name}: {exc}[/]")
                return downloaded

        try:
            fetched_files = _run(_do_fetch_all())
        except Exception as e:
            if not json_mode:
                console.print(f"[yellow][WARN] Ошибка скачивания файлов: {e}[/]")

    if json_mode:
        _output_json(
            {
                "pattern": res.pattern,
                "searched_directory": res.searched_directory,
                "total_found": res.total_found,
                "entries": [e.model_dump() for e in res.entries],
                "fetched_files": fetched_files,
            }
        )
        return

    console.print(
        f'\n[bold {OFFICIAL_THEME.blue}]🔍 Поиск файлов по маске:[/] [bold white]"{res.pattern}"[/] '
        f"в [dim]{res.searched_directory}[/] [dim]({res.total_found} совпадений)[/]\n"
    )

    if not res.entries:
        console.print("[dim]  (файлы не найдены)[/]\n")
        return

    table = Table(
        box=None,
        border_style=OFFICIAL_THEME.secondary,
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("#", style=f"bold {OFFICIAL_THEME.blue}", width=4)
    table.add_column("Имя", style="bold white", min_width=20)
    table.add_column("Размер", justify="right", min_width=10)
    table.add_column("Полный путь", style="dim", min_width=32)

    for i, entry in enumerate(res.entries, 1):
        table.add_row(
            str(i),
            entry.name,
            format_bytes(entry.size_bytes),
            entry.path,
        )

    console.print(table)
    if fetched_files:
        console.print(
            f"\n[bold {OFFICIAL_THEME.green}][OK] Скачано файлов в локальный карман: {len(fetched_files)}[/]"
        )
        for ff in fetched_files:
            console.print(f"  • {ff}")
    console.print()


# ---------------------------------------------------------------------------
# 3.5 Top-level Direct Send (Human Drop)
# ---------------------------------------------------------------------------


@app.command("send")
def cmd_send(
    files: list[Path] | None = typer.Argument(
        None, help="Пути к файлам для отправки в удалённый карман"
    ),
    from_clipboard: bool = typer.Option(
        False, "--clipboard", "-B", help="Взять файлы, скриншот или текст из буфера обмена"
    ),
    target_dir: str | None = typer.Option(
        None, "--target-dir", "-d", help="Относительный подкаталог в удаленном кармане"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла-получателя"),
) -> None:
    """Прямая отправка файлов в удалённый карман (Direct File Drop / Clipboard)."""
    client = _get_client(config, host, port, token, node)

    resolved_files: list[Path] = []

    # 1. Захват данных из буфера обмена
    if from_clipboard:
        clip_data = get_clipboard_content()
        if clip_data.data_type == "files" and clip_data.files:
            resolved_files.extend(clip_data.files)
            if not json_mode:
                console.print(
                    f"[bold cyan][CLIPBOARD][/] Найдено {len(clip_data.files)} файлов из буфера обмена"
                )
        elif clip_data.data_type == "image" and clip_data.image_bytes:
            filename = clip_data.suggested_filename or f"screenshot_{int(time.time())}.png"
            img_path = client.pocket_dir / filename
            try:
                img_path.write_bytes(clip_data.image_bytes)
                resolved_files.append(img_path)
                if not json_mode:
                    console.print(
                        f"[bold cyan][CLIPBOARD][/] Скриншот из буфера сохранён как [bold white]{filename}[/]"
                    )
            except Exception as e:
                _handle_error(
                    BridgeClientError(f"Ошибка сохранения скриншота из буфера: {e}"),
                    as_json=json_mode,
                )
                return
        elif clip_data.data_type == "text" and clip_data.text:
            filename = f"clipboard_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            txt_path = client.pocket_dir / filename
            try:
                txt_path.write_text(clip_data.text, encoding="utf-8")
                resolved_files.append(txt_path)
                if not json_mode:
                    console.print(
                        f"[bold cyan][CLIPBOARD][/] Текст из буфера сохранён как [bold white]{filename}[/]"
                    )
            except Exception as e:
                _handle_error(
                    BridgeClientError(f"Ошибка сохранения текста из буфера: {e}"), as_json=json_mode
                )
                return
        else:
            _handle_error(
                BridgeClientError(
                    "Буфер обмена пуст или не содержит файлов, изображений или текста."
                ),
                as_json=json_mode,
            )
            return

    # 2. Файлы из позиционных аргументов
    if files:
        for fp in files:
            resolved = fp.resolve()
            if not resolved.is_file():
                _handle_error(
                    BridgeClientError(f"Файл не найден или не является обычным файлом: {fp}"),
                    as_json=json_mode,
                )
                return
            resolved_files.append(resolved)

    if not resolved_files:
        _handle_error(
            BridgeClientError("Укажите файлы для отправки или используйте флаг --clipboard / -B"),
            as_json=json_mode,
        )
        return

    async def _action() -> list[dict[str, Any]]:
        results = []
        async with client:
            for resolved in resolved_files:
                target_rel = (
                    f"{target_dir.strip('/')}/{resolved.name}" if target_dir else resolved.name
                )
                file_size = resolved.stat().st_size
                res = await client.pocket_push_file(
                    resolved, target_rel_path=target_rel, target_node=node
                )
                results.append(
                    {
                        "file": resolved.name,
                        "local_path": str(resolved),
                        "target_rel_path": target_rel,
                        "sha256": res.sha256 or "",
                        "total_bytes": file_size,
                        "completed": res.completed,
                    }
                )
        return results

    try:
        data = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json({"sent": data, "count": len(data)})
        return

    for item in data:
        console.print(
            f"[bold {OFFICIAL_THEME.green}][OK][/] Отправлен [bold white]{item['file']}[/] "
            f"({item['total_bytes']} B, SHA-256: [dim]{item['sha256'][:12]}...[/]) ──► "
            f"[bold {OFFICIAL_THEME.blue}]{item['target_rel_path']}[/]"
        )


@app.command("drop")
def cmd_drop_alias(
    files: list[Path] | None = typer.Argument(
        None, help="Пути к файлам для отправки в удалённый карман"
    ),
    from_clipboard: bool = typer.Option(
        False, "--clipboard", "-B", help="Взять файлы, скриншот или текст из буфера обмена"
    ),
    target_dir: str | None = typer.Option(
        None, "--target-dir", "-d", help="Относительный подкаталог в удаленном кармане"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост удаленного узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт удаленного узла"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
    node: str | None = typer.Option(None, "--node", "-n", help="Имя узла-получателя"),
) -> None:
    """Быстрая отправка файлов в удалённый карман (алиас для send)."""
    cmd_send(
        files=files,
        from_clipboard=from_clipboard,
        target_dir=target_dir,
        json_mode=json_mode,
        config=config,
        host=host,
        port=port,
        token=token,
        node=node,
    )


# ---------------------------------------------------------------------------
# 4. Notes Subcommands
# ---------------------------------------------------------------------------


@note_app.command("send")
def cmd_note_send(
    text: str = typer.Argument(..., help="Текст записки или ссылка"),
    to_node: str | None = typer.Option(None, "--to", "-t", help="Узел-получатель"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Мгновенная отправка короткой заметки или ссылки на удаленный узел."""
    client = _get_client(config, host, port, token)

    async def _action() -> Any:
        async with client:
            return await client.note_send(text=text, target_node=to_node)

    try:
        delivery = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(delivery.model_dump())
        return

    console.print(
        f"[bold {OFFICIAL_THEME.green}][OK] Записка отправлена[/] "
        f"(id=[dim]{delivery.note_id}[/], status={delivery.status})"
    )


@note_app.command("list")
def cmd_note_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Максимум записок"),
    unread_only: bool = typer.Option(False, "--unread", "-u", help="Только непрочитанные"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Просмотр журнала заметок."""
    client = _get_client(config, host, port, token)

    async def _action() -> Any:
        async with client:
            return await client.note_history(limit=limit)

    try:
        hist = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    notes = hist.notes
    if unread_only:
        notes = [n for n in notes if n.status != "read"]

    if json_mode:
        _output_json({"total_count": len(notes), "notes": [n.model_dump() for n in notes]})
        return

    if not notes:
        console.print("[dim]Записок нет.[/]")
        return

    for n in notes:
        status_color = OFFICIAL_THEME.green if n.status == "delivered" else OFFICIAL_THEME.secondary
        console.print(
            f"[dim]{n.timestamp[:19]}[/] "
            f"[{status_color}][{n.status.upper()}][/] "
            f"[bold {OFFICIAL_THEME.purple}]{n.author_os}[/]: {n.text}"
        )


@note_app.command("read")
def cmd_note_read(
    note_ids: list[str] = typer.Argument(..., help="ID записок для отметки прочитанными"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост"),
    port: int | None = typer.Option(None, "--port", "-p", help="Порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Пометить одну или несколько записок как прочитанные."""
    client = _get_client(config, host, port, token)

    async def _action() -> Any:
        async with client:
            return await client.note_mark_read(note_ids=note_ids)

    try:
        res = _run(_action())
    except Exception as e:
        _handle_error(e, as_json=json_mode)
        return

    if json_mode:
        _output_json(res.model_dump())
        return

    console.print(f"[bold {OFFICIAL_THEME.green}][OK] Помечено прочитанными:[/] {res.marked_count}")


# ---------------------------------------------------------------------------
# 5. UI / TUI & Welcome Commands
# ---------------------------------------------------------------------------


@app.command("tui")
def cmd_tui(
    single_pass: bool = typer.Option(False, "--single-pass", help="Отрисовать один кадр без цикла"),
) -> None:
    """Запуск интерактивного Micro/Mini HUD Bridge Local."""
    run_interactive_tui(
        theme=OFFICIAL_THEME,
        single_pass=single_pass,
    )


# ---------------------------------------------------------------------------
# 5.5 LAN Zero-Conf Discovery (UDP Broadcast Beacon)
# ---------------------------------------------------------------------------


@app.command("scan")
def cmd_scan(
    timeout: float = typer.Option(1.5, "--timeout", "-t", help="Таймаут сканирования сети (сек)"),
    apply: bool = typer.Option(
        False, "--apply", "-a", help="Автоматически сохранить найденный узел в bridge.toml"
    ),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> None:
    """Поиск узлов Bridge Local в локальной сети (LAN Zero-Conf Discovery)."""
    cfg = BridgeConfig.load(config)
    psk = cfg.connection.psk_token or ""

    if not json_mode:
        console.print(
            f"[bold {OFFICIAL_THEME.blue}]🔍 Поиск узлов Bridge Local в локальной сети (UDP broadcast 9735)...[/]"
        )

    import asyncio

    from bridge_core.discovery import discover_nodes

    source_node = cfg.node.name or "workstation-linux"
    nodes = asyncio.run(
        discover_nodes(
            psk_token=psk,
            timeout_sec=timeout,
            source_node=source_node,
        )
    )

    if json_mode:
        _output_json(
            {
                "found": len(nodes),
                "nodes": [n.model_dump() for n in nodes],
            }
        )
        return

    if not nodes:
        console.print("[bold yellow][!] Узлы Bridge Local не обнаружены в локальной сети.[/]")
        console.print(
            "[dim]Убедитесь, что агент запущен на Windows и UDP-порт 9735 разрешён в брандмауэре.[/]"
        )
        return

    console.print(f"\n[bold {OFFICIAL_THEME.green}][OK] Обнаружено узлов: {len(nodes)}[/]\n")
    table = Table(
        title="[bold white]НАЙДЕННЫЕ УЗЛЫ BRIDGE LOCAL (LAN ZERO-CONF)[/]",
        border_style=OFFICIAL_THEME.secondary,
        show_lines=True,
    )
    table.add_column("#", style=f"bold {OFFICIAL_THEME.blue}", width=4)
    table.add_column("Узел", style="bold white")
    table.add_column("IP : Port", style=f"bold {OFFICIAL_THEME.green}")
    table.add_column("ОС", style=f"bold {OFFICIAL_THEME.purple}")
    table.add_column("PSK Статус", style="bold")
    table.add_column("Пинг", style="dim", justify="right")

    for i, n in enumerate(nodes, 1):
        psk_badge = (
            f"[bold {OFFICIAL_THEME.green}]✓ ПОДТВЕРЖДЁН[/]"
            if n.psk_valid
            else f"[bold {OFFICIAL_THEME.red}]✗ НЕ СОВПАДАЕТ[/]"
        )
        table.add_row(
            str(i),
            f"{n.node_name} [dim]({n.display_name or n.os})[/]",
            f"{n.ip}:{n.port}",
            n.os.capitalize(),
            psk_badge,
            f"{n.latency_ms:.1f} мс",
        )
    console.print(table)

    selected_node = None
    if apply:
        selected_node = next((n for n in nodes if n.psk_valid), nodes[0])
    elif sys.stdin.isatty():
        console.print("\n[dim]Введите номер узла для подключения или Enter для выхода:[/]")
        with contextlib.suppress(Exception):
            choice = input("  > ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(nodes):
                selected_node = nodes[int(choice) - 1]

    if selected_node:
        cfg.update_connection(host=selected_node.ip, port=selected_node.port)
        cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
        console.print(
            f"\n[bold {OFFICIAL_THEME.green}][OK] Адрес узла {selected_node.ip}:{selected_node.port} сохранён в {cfg_name}![/]"
        )


# ---------------------------------------------------------------------------
# 6. Config Subcommands
# ---------------------------------------------------------------------------


@config_app.command("show")
def cmd_config_show(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Отображение текущей конфигурации."""
    cfg = BridgeConfig.load(config)
    if json_mode:
        _output_json(cfg.model_dump())
        return
    console.print(
        Panel(
            cfg.to_toml_string(),
            title="[bold white]BRIDGE LOCAL CONFIGURATION (TOML)[/]",
            border_style=OFFICIAL_THEME.secondary,
        )
    )


@config_app.command("set")
def cmd_config_set(
    host: str | None = typer.Option(None, "--host", "-h", help="IP-адрес или hostname узла"),
    port: int | None = typer.Option(None, "--port", "-p", help="TCP порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="Ключ безопасности PSK"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Машиночитаемый вывод JSON"),
) -> None:
    """Установка сетевых параметров в bridge.toml через CLI."""
    if host is None and port is None and token is None:
        console.print("[bold red]Укажите хотя бы один параметр: --host, --port или --token[/]")
        raise typer.Exit(code=ExitCode.GENERAL_ERROR)

    cfg = BridgeConfig.load(config)
    cfg.update_connection(host=host, port=port, psk_token=token, save=True)

    if json_mode:
        _output_json(
            {
                "status": "success",
                "host": cfg.connection.host,
                "port": cfg.connection.port,
                "psk_set": bool(cfg.connection.psk_token),
                "config_path": str(cfg._config_path or "bridge.toml"),
            }
        )
        return

    console.print(f"[bold green][OK] Параметры сохранены в {cfg._config_path or 'bridge.toml'}[/]")
    console.print(f"  Хост: [bold white]{cfg.connection.host}[/]")
    console.print(f"  Порт: [bold white]{cfg.connection.port}[/]")


@config_app.command("path")
def cmd_config_path(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Выводит абсолютный путь к активному файлу конфигурации."""
    cfg = BridgeConfig.load(config)
    active_path = str(cfg._config_path.resolve()) if cfg._config_path else "bridge.toml (default)"
    if json_mode:
        exists = bool(cfg._config_path and cfg._config_path.exists())
        _output_json({"config_path": active_path, "exists": exists})
        return
    console.print(active_path)


@app.command("connect")
def cmd_connect(
    target: str = typer.Argument(
        ...,
        help="Адрес целевого узла Windows (например: 192.168.1.150:9732 или 192.168.1.150)",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="PSK токен аутентификации (опционально)",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Путь к файлу конфигурации bridge.toml",
    ),
    json_mode: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Машиночитаемый вывод JSON",
    ),
) -> None:
    """Быстрое подключение и сохранение адреса узла без ручного редактирования TOML."""
    from bridge_client_linux.tui.app import probe_target_socket

    raw_target = target.replace("http://", "").replace("https://", "").strip()
    cfg = BridgeConfig.load(config)
    cur_host = cfg.connection.host
    cur_port = cfg.connection.port

    new_host = cur_host
    new_port = cur_port

    if raw_target.startswith(":"):
        with contextlib.suppress(ValueError):
            new_port = int(raw_target[1:].strip())
    elif ":" in raw_target:
        parts = raw_target.split(":", 1)
        new_host = parts[0].strip()
        with contextlib.suppress(ValueError):
            new_port = int(parts[1].strip())
    else:
        new_host = raw_target

    cfg.update_connection(host=new_host, port=new_port, psk_token=token, save=True)
    is_online, latency = probe_target_socket(new_host, new_port, timeout_sec=0.4)

    if json_mode:
        _output_json(
            {
                "status": "success",
                "host": new_host,
                "port": new_port,
                "is_online": is_online,
                "latency_ms": latency if is_online else None,
                "config_path": str(cfg._config_path or "bridge.toml"),
            }
        )
        return

    status_str = (
        f"[bold green]ONLINE[/] (пинг {latency:.2f} мс)"
        if is_online
        else "[bold red]OFFLINE[/] (узел не отвечает, проверьте запуск службы)"
    )
    console.print(
        Panel(
            f"[bold white]Настройки подключения успешно обновлены![/]\n\n"
            f"  • [bold cyan]Целевой хост:[/]"
            f"   [bold white]{new_host}[/]\n"
            f"  • [bold magenta]Порт:[/]"
            f"           [bold white]{new_port}[/]\n"
            f"  • [bold yellow]Статус сокета:[/]"
            f"  {status_str}\n"
            f"  • [dim]Конфигурация:[/]  [dim]{cfg._config_path or 'bridge.toml'}[/]\n\n"
            f"[dim]Для запуска мониторинга введите: bridge tui[/]",
            title="[bold green]BRIDGE LOCAL: ПОДКЛЮЧЕНИЕ НАСТРОЕНО[/]",
            border_style=OFFICIAL_THEME.green if is_online else OFFICIAL_THEME.amber,
        )
    )


@app.command("setup")
def cmd_setup(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Путь к файлу конфигурации bridge.toml",
    ),
) -> None:
    """Интерактивный мастер первоначальной настройки подключения без ручной правки TOML."""
    from bridge_client_linux.tui.app import probe_target_socket

    console.print("[bold cyan]════════════════════════════════════════════════════════════[/]")
    console.print("[bold white]  Bridge Local (Linux Client) — Мастер настройки подключения[/]")
    console.print("[bold cyan]════════════════════════════════════════════════════════════[/]\n")

    cfg = BridgeConfig.load(config)
    cur_host = cfg.connection.host
    cur_port = cfg.connection.port
    cur_token = cfg.connection.psk_token or ""

    console.print(f"[dim]Текущие параметры ({cfg._config_path or 'bridge.toml'}):[/]")
    console.print(f"  Хост: [bold white]{cur_host}[/]")
    console.print(f"  Порт: [bold white]{cur_port}[/]")
    token_display = f"{cur_token[:8]}..." if cur_token else "(отключен)"
    console.print(f"  Токен: [bold white]{token_display}[/]")
    console.print("")

    val_host = typer.prompt(
        "1. Введите IP-адрес или Hostname Windows-машины",
        default=cur_host,
    ).strip()

    val_port = typer.prompt(
        "2. Введите TCP-порт",
        default=str(cur_port),
    ).strip()

    val_token = typer.prompt(
        "3. Введите PSK-токен (Enter для сохранения текущего)",
        default=cur_token,
        show_default=False,
    ).strip()

    port_int = int(val_port) if val_port.isdigit() else cur_port
    cfg.update_connection(host=val_host, port=port_int, psk_token=val_token, save=True)

    is_online, latency = probe_target_socket(val_host, port_int, timeout_sec=0.4)
    status_str = (
        f"[bold green]ONLINE[/] (пинг {latency:.2f} мс)"
        if is_online
        else "[bold red]OFFLINE[/] (узел не отвечает)"
    )

    console.print("\n[bold green][OK] Настройки успешно сохранены![/]")
    console.print(f"Цель: [bold white]{val_host}:{port_int}[/] — {status_str}")
    console.print("[dim]Запустите 'bridge tui' для перехода в оперативный интерфейс.[/]")


# ---------------------------------------------------------------------------
# 7. Token Security Command
# ---------------------------------------------------------------------------


@app.command("token")
def cmd_token(
    value: str | None = typer.Argument(None, help="Новый PSK-токен для установки"),
    generate: bool = typer.Option(
        False, "--generate", "-g", help="Сгенерировать случайный 32-байтный токен"
    ),
    copy_to_clip: bool = typer.Option(
        False, "--copy", "-c", help="Скопировать токен в буфер обмена"
    ),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", help="Путь к bridge.toml"),
) -> None:
    """Управление секретным PSK-токеном аутентификации."""
    cfg = BridgeConfig.load(config)
    cfg_file = cfg._config_path or Path("bridge.toml")

    # 1. Генерация нового токена
    if generate:
        new_token = secrets.token_urlsafe(32)
        cfg.connection.psk_token = new_token
        cfg.save(cfg_file)
        copied = False
        if copy_to_clip:
            copied = copy_text_to_clipboard(new_token)
        fp = hashlib.sha256(new_token.encode("utf-8")).hexdigest()[:12]
        if json_mode:
            _output_json(
                {
                    "status": "generated",
                    "token": new_token,
                    "fingerprint": fp,
                    "copied_to_clipboard": copied,
                    "config_path": str(cfg_file),
                }
            )
            return
        console.print(f"[bold {OFFICIAL_THEME.green}][OK] Сгенерирован и сохранён новый токен:[/]")
        console.print(f"  Токен:        [bold white]{new_token}[/]")
        console.print(f"  Отпечаток:    [dim]{fp}[/]")
        console.print(f"  Конфигурация: [dim]{cfg_file}[/]")
        if copy_to_clip:
            status_txt = (
                "скопирован в буфер обмена"
                if copied
                else "не удалось скопировать (нет wl-copy/xclip)"
            )
            console.print(f"  [bold cyan]• Токен {status_txt}[/]")
        return

    # 2. Установка переданного токена
    if value is not None:
        val_clean = value.strip()
        if len(val_clean) < 8:
            _handle_error(
                BridgeClientError("Токен слишком короткий. Минимальная длина — 8 символов."),
                as_json=json_mode,
            )
            return
        cfg.connection.psk_token = val_clean
        cfg.save(cfg_file)
        copied = False
        if copy_to_clip:
            copied = copy_text_to_clipboard(val_clean)
        fp = hashlib.sha256(val_clean.encode("utf-8")).hexdigest()[:12]
        if json_mode:
            _output_json(
                {
                    "status": "updated",
                    "token_set": True,
                    "fingerprint": fp,
                    "copied_to_clipboard": copied,
                    "config_path": str(cfg_file),
                }
            )
            return
        console.print(f"[bold {OFFICIAL_THEME.green}][OK] Токен успешно обновлён в {cfg_file}[/]")
        console.print(f"  Отпечаток:    [dim]{fp}[/]")
        if copy_to_clip:
            status_txt = "скопирован в буфер обмена" if copied else "не удалось скопировать"
            console.print(f"  [bold cyan]• Токен {status_txt}[/]")
        return

    # 3. Просто копирование текущего токена
    cur_token = cfg.connection.psk_token or ""
    if copy_to_clip:
        if not cur_token:
            _handle_error(
                BridgeClientError("Токен не задан в конфигурации."),
                as_json=json_mode,
            )
            return
        copied = copy_text_to_clipboard(cur_token)
        if json_mode:
            _output_json(
                {
                    "status": "copied" if copied else "failed",
                    "copied_to_clipboard": copied,
                }
            )
            return
        if copied:
            console.print(
                f"[bold {OFFICIAL_THEME.green}][OK] Текущий токен скопирован в буфер обмена.[/]"
            )
        else:
            console.print(
                "[bold yellow][!] Не удалось скопировать в буфер (утилита wl-copy/xclip не найдена).[/]"
            )
        return

    # 4. Просмотр текущего токена
    fp = hashlib.sha256(cur_token.encode("utf-8")).hexdigest()[:12] if cur_token else "none"
    masked = (
        f"{cur_token[:4]}...{cur_token[-4:]}"
        if len(cur_token) >= 8
        else ("(не задан)" if not cur_token else "***")
    )
    if json_mode:
        _output_json(
            {
                "token_set": bool(cur_token),
                "masked": masked,
                "fingerprint": fp,
                "config_path": str(cfg_file),
            }
        )
        return
    console.print(f"[bold cyan]Параметры токена безопасности ({cfg_file}):[/]")
    console.print(
        f"  Статус:    {'[bold green]АКТИВЕН[/]' if cur_token else '[bold yellow]ОТКЛЮЧЕН[/]'}"
    )
    console.print(f"  Токен:     [bold white]{masked}[/]")
    console.print(f"  Отпечаток: [dim]{fp}[/]")
    console.print("\n[dim]Подсказка: bridge-cli token -g -c (сгенерировать и скопировать)[/]")


# ---------------------------------------------------------------------------
# 8. Service & Daemon Management Subcommands
# ---------------------------------------------------------------------------

SERVICE_PID_FILE_NAME = ".bridge_service.pid"


def _get_service_pid_file(pocket_dir: Path) -> Path:
    return pocket_dir / SERVICE_PID_FILE_NAME




@service_app.command("run")
def cmd_service_run(
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
    host: str | None = typer.Option(None, "--host", "-h", help="Хост прослушивания"),
    port: int | None = typer.Option(None, "--port", "-p", help="TCP порт"),
    token: str | None = typer.Option(None, "--token", "-t", help="PSK токен"),
) -> None:
    """Запуск службы Bridge Local в интерактивном режиме консоли (Foreground)."""
    cfg = BridgeConfig.load(config)
    if host:
        cfg.connection.host = host
    if port:
        cfg.connection.port = port
    if token:
        cfg.connection.psk_token = token

    bind_host = cfg.connection.host
    if bind_host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        bind_host = "0.0.0.0"

    pocket_dir = cfg.get_pocket_dir()
    console.print(
        Panel(
            f"[bold {OFFICIAL_THEME.green}]◈ BRIDGE LOCAL SERVICE (LINUX NODE) ◈[/]\n\n"
            f"  [bold white]Слушатель:[/]   {bind_host}:{cfg.connection.port}\n"
            f"  [bold white]Исполнитель:[/] BashExecutor (Linux Bash & Non-blocking I/O)\n"
            f"  [bold white]Карман:[/]      {pocket_dir}\n"
            f"  [bold white]Безопасность:[/] {'PSK HMAC-SHA256' if cfg.connection.psk_token else 'ОТКЛЮЧЕНА (Открытый режим)'}\n\n"
            f"[dim]Нажмите Ctrl+C для штатной остановки службы.[/]",
            border_style=OFFICIAL_THEME.blue,
        )
    )

    service = BridgeService(config=cfg)

    async def _runner() -> None:
        await service.run_forever()

    try:
        asyncio.run(_runner())
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[bold yellow][SERVICE] Получен сигнал прерывания, служба остановлена.[/]")
    except Exception as e:
        console.print(f"\n[bold red][ERROR] Критическая ошибка службы: {e}[/]")
        raise typer.Exit(code=ExitCode.GENERAL_ERROR) from e


@service_app.command("start")
def cmd_service_start(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Запуск службы Bridge Local в виде независимого фонового демона (Detached)."""
    cfg = BridgeConfig.load(config)
    port = cfg.connection.port
    pocket_dir = cfg.get_pocket_dir()
    pid_file = _get_service_pid_file(pocket_dir)

    # Проверка: не слушает ли уже порт локально
    if _check_port_listening("127.0.0.1", port):
        msg = f"Служба Bridge Local уже запущена и слушает порт {port}."
        if json_mode:
            _output_json({"status": "already_running", "port": port, "message": msg})
            return
        console.print(f"[bold yellow][INFO][/] {msg}")
        return

    # Проверка PID файла
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            if _is_pid_alive(old_pid):
                msg = f"Фоновый процесс службы уже активен (PID={old_pid})."
                if json_mode:
                    _output_json({"status": "already_running", "pid": old_pid, "message": msg})
                    return
                console.print(f"[bold yellow][INFO][/] {msg}")
                return
        except Exception:
            pass

    # Формируем команду запуска
    if getattr(sys, "frozen", False):
        exec_cmd = [sys.executable, "service", "run"]
    else:
        exec_cmd = [sys.executable, "-m", "bridge_client_linux.cli", "service", "run"]
    if config:
        exec_cmd.extend(["-c", str(config)])

    try:
        # Detached process with setsid
        proc = subprocess.Popen(
            exec_cmd,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            cwd=str(pocket_dir.parent) if pocket_dir.parent.exists() else str(Path.cwd()),
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))

        # Ожидание открытия порта
        online = False
        for _ in range(25):
            time.sleep(0.1)
            if _check_port_listening("127.0.0.1", port, timeout_sec=0.1):
                online = True
                break

        res_payload = {
            "status": "started",
            "pid": proc.pid,
            "port": port,
            "port_listening": online,
        }
        if json_mode:
            _output_json(res_payload)
            return

        if online:
            console.print(
                f"[bold {OFFICIAL_THEME.green}][OK] Фоновый демон Bridge Local успешно запущен "
                f"(PID={proc.pid}, порт {port}).[/]"
            )
        else:
            console.print(
                f"[bold yellow][INFO] Процесс запущен (PID={proc.pid}), ожидает активации порта {port}.[/]"
            )
    except Exception as e:
        _handle_error(e, as_json=json_mode)


@service_app.command("stop")
def cmd_service_stop(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Остановка фонового демона службы Bridge Local."""
    cfg = BridgeConfig.load(config)
    pocket_dir = cfg.get_pocket_dir()
    pid_file = _get_service_pid_file(pocket_dir)

    target_pid = None
    if pid_file.exists():
        with contextlib.suppress(Exception):
            target_pid = int(pid_file.read_text().strip())

    killed = False
    if target_pid and _is_pid_alive(target_pid):
        kill_process_tree(target_pid, timeout_sec=3.0)
        killed = True

    with contextlib.suppress(Exception):
        if pid_file.exists():
            pid_file.unlink()

    if json_mode:
        _output_json({"status": "stopped", "killed": killed, "pid": target_pid})
        return

    if killed:
        console.print(f"[bold {OFFICIAL_THEME.green}][OK] Фоновый демон (PID={target_pid}) успешно остановлен.[/]")
    else:
        console.print("[dim]Активный фоновый демон не обнаружен.[/]")


@service_app.command("status")
def cmd_service_status(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Проверка статуса работы локальной службы узла (PID, порт, метрики, systemd)."""
    cfg = BridgeConfig.load(config)
    port = cfg.connection.port
    pocket_dir = cfg.get_pocket_dir()
    pid_file = _get_service_pid_file(pocket_dir)

    pid = None
    pid_alive = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            pid_alive = _is_pid_alive(pid)
        except Exception:
            pass

    port_open = _check_port_listening("127.0.0.1", port)

    # Проверка systemd user службы
    systemd_active = False
    systemd_installed = False
    systemctl_path = shutil.which("systemctl")
    if systemctl_path:
        with contextlib.suppress(Exception):
            chk = subprocess.run(
                ["systemctl", "--user", "is-active", "bridge-local.service"],
                capture_output=True,
                text=True,
                check=False,
            )
            systemd_active = chk.stdout.strip() == "active"
            unit_file = Path.home() / ".config" / "systemd" / "user" / "bridge-local.service"
            systemd_installed = unit_file.exists()

    # Попытка локального пинга для получения метрик
    metrics: dict[str, Any] | None = None
    if port_open:
        try:
            client = BridgeClient(
                config=cfg,
                host="127.0.0.1",
                port=port,
                psk_token=cfg.connection.psk_token,
                timeout_sec=1.5,
            )

            async def _ping_local() -> dict[str, Any]:
                async with client:
                    pong, rtt = await client.ping(client_os=NodeOS.LINUX)
                    return {"latency_ms": rtt, "pong": pong.model_dump()}

            metrics = _run(_ping_local())
        except Exception:
            pass

    status_data = {
        "running": port_open or pid_alive or systemd_active,
        "pid": pid,
        "pid_alive": pid_alive,
        "port": port,
        "port_listening": port_open,
        "systemd_installed": systemd_installed,
        "systemd_active": systemd_active,
        "metrics": metrics,
    }

    if json_mode:
        _output_json(status_data)
        return

    table = Table(title="◈ BRIDGE LOCAL SERVICE STATUS (LINUX NODE) ◈", expand=True)
    table.add_column("Компонент", style="bold white", width=24)
    table.add_column("Параметры", style="dim white")
    table.add_column("Статус", justify="center")

    table.add_row(
        "Порт службы",
        f"0.0.0.0:{port}",
        "[bold green]LISTENING[/]" if port_open else "[dim red]CLOSED[/]",
    )
    table.add_row(
        "Фоновый PID",
        f"PID={pid}" if pid else "нет файла PID",
        "[bold green]RUNNING[/]" if pid_alive else "[dim]INACTIVE[/]",
    )
    if systemctl_path:
        table.add_row(
            "Systemd User Unit",
            "bridge-local.service",
            "[bold green]ACTIVE[/]" if systemd_active else ("[dim yellow]INSTALLED[/]" if systemd_installed else "[dim]NOT INSTALLED[/]"),
        )
    if metrics:
        p = metrics["pong"]
        table.add_row(
            "Метрики узла",
            f"CPU: {p['cpu_percent']}% · RAM: {p['memory_used_mb']} MB · Uptime: {p['uptime_seconds']}s",
            f"[bold green]{p['status'].upper()}[/]",
        )

    console.print(table)


@service_app.command("install-systemd")
def cmd_service_install_systemd(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к bridge.toml"),
) -> None:
    """Генерация и активация пользовательского systemd-юнита (bridge-local.service)."""
    systemctl = shutil.which("systemctl")
    if not systemctl:
        _handle_error(BridgeClientError("Утилита systemctl не найдена в системе."), as_json=json_mode)
        return

    # Определение пути исполняемого файла
    bridge_cli = shutil.which("bridge-cli")
    if bridge_cli:
        exec_start = f"{bridge_cli} service run"
    elif getattr(sys, "frozen", False):
        exec_start = f"{sys.executable} service run"
    else:
        exec_start = f"{sys.executable} -m bridge_client_linux.cli service run"

    if config:
        exec_start += f" -c {config.resolve()}"

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "bridge-local.service"

    unit_content = f"""[Unit]
Description=Bridge Local Universal P2P Peer Service
Documentation=https://github.com/Anhelm01/Bridge_Local
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=3s
Environment=PYTHONUNBUFFERED=1
Environment=LD_PRELOAD=

[Install]
WantedBy=default.target
"""
    unit_path.write_text(unit_content, encoding="utf-8")

    # Перезагрузка и включение юнита
    subprocess.run([systemctl, "--user", "daemon-reload"], capture_output=True, text=True, check=False)
    enable_res = subprocess.run([systemctl, "--user", "enable", "--now", "bridge-local.service"], capture_output=True, text=True, check=False)

    success = enable_res.returncode == 0
    res_data = {
        "status": "installed" if success else "failed",
        "unit_path": str(unit_path),
        "enabled": success,
        "error": enable_res.stderr if not success else None,
    }

    if json_mode:
        _output_json(res_data, exit_code=ExitCode.SUCCESS if success else ExitCode.GENERAL_ERROR)
        return

    if success:
        console.print(f"[bold {OFFICIAL_THEME.green}][OK] Systemd служба успешно установлена и запущена![/]")
        console.print(f"  Файл юнита: [bold white]{unit_path}[/]")
        console.print("  Команда:    [dim]systemctl --user status bridge-local.service[/]")
    else:
        console.print(f"[bold red][ERROR] Ошибка активации службы: {enable_res.stderr}[/]")
        raise typer.Exit(code=ExitCode.GENERAL_ERROR)


@service_app.command("uninstall-systemd")
def cmd_service_uninstall_systemd(
    json_mode: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> None:
    """Отключение и удаление пользовательского systemd-юнита (bridge-local.service)."""
    systemctl = shutil.which("systemctl")
    unit_path = Path.home() / ".config" / "systemd" / "user" / "bridge-local.service"

    if systemctl:
        subprocess.run([systemctl, "--user", "disable", "--now", "bridge-local.service"], capture_output=True, text=True, check=False)

    if unit_path.exists():
        unit_path.unlink()

    if systemctl:
        subprocess.run([systemctl, "--user", "daemon-reload"], capture_output=True, text=True, check=False)

    if json_mode:
        _output_json({"status": "uninstalled", "unit_path": str(unit_path)})
        return

    console.print(f"[bold {OFFICIAL_THEME.green}][OK] Служба bridge-local.service отключена и удалена.[/]")


def run() -> None:
    """Точка запуска CLI через sys.argv."""
    # Защита от перехвата локальных LAN сокетов proxychains
    if "proxychains" in os.environ.get("LD_PRELOAD", "") and not os.environ.get(
        "BRIDGE_NO_PROXY_BYPASS"
    ):
        env = dict(os.environ)
        preloads = [p for p in env.get("LD_PRELOAD", "").split(":") if "proxychains" not in p]
        if preloads:
            env["LD_PRELOAD"] = ":".join(preloads)
        else:
            env.pop("LD_PRELOAD", None)
        env["BRIDGE_NO_PROXY_BYPASS"] = "1"
        exec_args = (
            [sys.executable, *sys.argv[1:]]
            if getattr(sys, "frozen", False)
            else [sys.executable, *sys.argv]
        )
        with contextlib.suppress(Exception):
            os.execvpe(sys.executable, exec_args, env)

    app()


if __name__ == "__main__":
    run()
