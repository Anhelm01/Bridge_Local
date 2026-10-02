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
import json
import os
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bridge_client_linux.client import BridgeClient
from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeRemoteCommandError,
    BridgeTimeoutError,
)
from bridge_client_linux.exit_codes import ExitCode
from bridge_client_linux.tui.app import run_interactive_tui
from bridge_client_linux.tui.screens import render_welcome_screen
from bridge_client_linux.tui.theme import OFFICIAL_THEME
from bridge_core.config import BridgeConfig

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

app.add_typer(pocket_app, name="pocket")
app.add_typer(note_app, name="note")
app.add_typer(config_app, name="config")

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
    if isinstance(e, BridgeAuthError):
        code = ExitCode.AUTH_ERROR
    elif isinstance(e, BridgeNetworkError):
        code = ExitCode.NETWORK_ERROR
    elif isinstance(e, BridgeTimeoutError):
        code = ExitCode.TIMEOUT
    elif isinstance(e, BridgeRemoteCommandError):
        code = ExitCode.COMMAND_FAILED
    elif isinstance(e, BridgeClientError):
        code = e.exit_code
    else:
        code = ExitCode.GENERAL_ERROR

    if as_json:
        payload: dict[str, Any] = {
            "status": "error",
            "error_code": int(code),
            "error_type": type(e).__name__,
            "message": str(e),
        }
        if isinstance(e, BridgeRemoteCommandError):
            payload["cmd_exit_code"] = e.cmd_exit_code
            payload["stdout"] = e.stdout
            payload["stderr"] = e.stderr
        _output_json(payload, exit_code=code)
    else:
        console.print(f"[bold red][ERROR {int(code)}][/] {e}")
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
        ver_info = {"version": "0.1.0", "core": "bridge_core", "target": "Linux/Windows"}
        if json_mode:
            _output_json(ver_info)
        else:
            console.print("[bold white]Bridge Local[/] v0.1.0 (Phase 5: Linux CLI & TUI)")
        raise typer.Exit()

    # Если команда не задана:
    if ctx.invoked_subcommand is None:
        if json_mode:
            _output_json({"status": "ready", "hint": "Use 'bridge-cli --help' for commands"})
            raise typer.Exit()
        if sys.stdin.isatty():
            # Запуск TUI в интерактивном терминале
            run_interactive_tui(theme=OFFICIAL_THEME, initial_mode="WELCOME")
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
        console.print(
            f"[bold {OFFICIAL_THEME.blue}][SYNC-WATCH] Автоматическая синхронизация кармана "
            f"запущена (интервал {interval}с)...[/]"
        )
        console.print("[dim]Для остановки нажмите Ctrl+C[/]\n")
        import time
        from datetime import datetime

        while True:
            try:
                summary = _run(_action())
                if summary.pulled or summary.pushed or summary.errors:
                    now_str = datetime.now().strftime("%H:%M:%S")
                    console.print(
                        f"[{now_str}] [bold {OFFICIAL_THEME.green}]Событие кармана:[/] "
                        f"Pulled: [bold {OFFICIAL_THEME.blue}]{len(summary.pulled)}[/], "
                        f"Pushed: [bold {OFFICIAL_THEME.amber}]{len(summary.pushed)}[/]"
                    )
                    for p in summary.pulled:
                        console.print(f"  ↓ Получен: [cyan]{p}[/]")
                    for p in summary.pushed:
                        console.print(f"  ↑ Отправлен: [green]{p}[/]")
            except KeyboardInterrupt:
                console.print(
                    f"\n[bold {OFFICIAL_THEME.amber}][SYNC-WATCH] Синхронизация остановлена.[/]"
                )
                break
            except Exception:
                pass
            time.sleep(interval)
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
    files: list[Path] = typer.Argument(..., help="Пути к файлам для отправки в карман"),
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
        target_dir=target_dir,
        json_mode=json_mode,
        config=config,
        host=host,
        port=port,
        token=token,
        node=node,
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
# 3.5 Top-level Direct Send (Human Drop)
# ---------------------------------------------------------------------------


@app.command("send")
def cmd_send(
    files: list[Path] = typer.Argument(..., help="Пути к файлам для отправки в удалённый карман"),
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
    """Прямая отправка файлов в удалённый карман (Direct File Drop)."""
    client = _get_client(config, host, port, token, node)

    # Предварительная валидация существования файлов до сетевого подключения
    resolved_files: list[Path] = []
    for fp in files:
        resolved = fp.resolve()
        if not resolved.is_file():
            _handle_error(
                BridgeClientError(f"Файл не найден или не является обычным файлом: {fp}"),
                as_json=json_mode,
            )
            return
        resolved_files.append(resolved)

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


@app.command("welcome")
def cmd_welcome() -> None:
    """Вывести полноэкранный Neofetch экран приветствия BRIDGES Master."""
    render_welcome_screen(OFFICIAL_THEME)


@app.command("tui")
def cmd_tui(
    mode: str = typer.Option(
        "DASH",
        "--mode",
        "-m",
        help="Начальный режим: DASH | POCKET | NOTES | EXEC | CONFIG | DEV",
    ),
    single_pass: bool = typer.Option(False, "--single-pass", help="Отрисовать один кадр без цикла"),
) -> None:
    """Запуск интерактивного полноэкранного TUI."""
    run_interactive_tui(theme=OFFICIAL_THEME, initial_mode=mode, single_pass=single_pass)


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
