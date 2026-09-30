"""
Unit tests for bridge-cli (Linux Typer CLI & AI Operator interface).
Verifies:
  - Clean, token-efficient JSON outputs (--json) without ANSI escapes.
  - Deterministic exit codes (0 = Success, 2 = Network Error, 3 = Auth Error, 4 = Command Failed).
  - All subcommands: status, ping, exec, pocket (status/sync/push/pull),
    note (send/list/read), config, welcome, tui.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bridge_agent_win.service import WindowsBridgeService
from bridge_client_linux.cli import app
from bridge_client_linux.exit_codes import ExitCode
from bridge_core.config import BridgeConfig, ConnectionConfig, PocketConfig

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="bridge_client_linux CLI tests run on Linux runners",
)

runner = CliRunner()


@pytest.fixture
def cli_server(tmp_path: Path):
    """Запускает реальный сервер в фоновом потоке со своим event loop."""
    pocket_dir = tmp_path / "pocket_server"
    pocket_dir.mkdir(parents=True, exist_ok=True)

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    service = WindowsBridgeService(cfg)
    loop = asyncio.new_event_loop()
    port_box: list[int] = []

    def _worker():
        asyncio.set_event_loop(loop)

        async def _run_srv():
            await service.start()
            assert service.server._server is not None
            port = service.server._server.sockets[0].getsockname()[1]
            port_box.append(port)

        loop.run_until_complete(_run_srv())
        loop.run_forever()

    th = threading.Thread(target=_worker, daemon=True)
    th.start()

    while not port_box:
        time.sleep(0.01)

    port = port_box[0]
    try:
        yield service, port, pocket_dir
    finally:

        async def _stop():
            await service.stop()

        asyncio.run_coroutine_threadsafe(_stop(), loop).result(timeout=3.0)
        loop.call_soon_threadsafe(loop.stop)
        th.join(timeout=2.0)


@pytest.fixture
def cli_auth_server(tmp_path: Path):
    """Запускает сервер с PSK-аутентификацией в фоновом потоке."""
    pocket_dir = tmp_path / "pocket_auth_server"
    pocket_dir.mkdir(parents=True, exist_ok=True)

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0, psk_token="correct-secret"),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    service = WindowsBridgeService(cfg)
    loop = asyncio.new_event_loop()
    port_box: list[int] = []

    def _worker():
        asyncio.set_event_loop(loop)

        async def _run_srv():
            await service.start()
            assert service.server._server is not None
            port = service.server._server.sockets[0].getsockname()[1]
            port_box.append(port)

        loop.run_until_complete(_run_srv())
        loop.run_forever()

    th = threading.Thread(target=_worker, daemon=True)
    th.start()

    while not port_box:
        time.sleep(0.01)

    port = port_box[0]
    try:
        yield service, port, pocket_dir
    finally:

        async def _stop():
            await service.stop()

        asyncio.run_coroutine_threadsafe(_stop(), loop).result(timeout=3.0)
        loop.call_soon_threadsafe(loop.stop)
        th.join(timeout=2.0)


def test_cli_version():
    """Тест --version в обычном и JSON режиме."""
    res_human = runner.invoke(app, ["--version"])
    assert res_human.exit_code == 0
    assert "Bridge Local" in res_human.stdout

    res_json = runner.invoke(app, ["--version", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert data["version"] == "0.1.0"
    assert data["core"] == "bridge_core"


def test_cli_config_show(tmp_path: Path):
    """Тест config show в JSON режиме."""
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig().save(cfg_file)

    res = runner.invoke(app, ["config", "show", "--config", str(cfg_file), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "connection" in data
    assert "pocket" in data


def test_cli_ping(cli_server, tmp_path: Path):
    """Тест ping в человеческом и JSON режимах."""
    _, port, _ = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    # JSON режим
    res = runner.invoke(app, ["ping", "--port", str(port), "--config", str(cfg_file), "--json"])
    assert res.exit_code == ExitCode.SUCCESS
    data = json.loads(res.stdout)
    assert "pings" in data
    assert len(data["pings"]) == 1
    assert data["pings"][0]["pong"]["status"] in ("ready", "busy")

    # Человеческий режим
    res_human = runner.invoke(app, ["ping", "--port", str(port), "--config", str(cfg_file)])
    assert res_human.exit_code == ExitCode.SUCCESS
    assert "PONG" in res_human.stdout


def test_cli_status(cli_server, tmp_path: Path):
    """Тест команды status."""
    _, port, _ = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    res = runner.invoke(app, ["status", "--port", str(port), "--config", str(cfg_file), "--json"])
    assert res.exit_code == ExitCode.SUCCESS
    data = json.loads(res.stdout)
    assert data["connection"]["status"] == "online"
    assert "pocket" in data
    assert "notes" in data


def test_cli_exec_success_and_failure(cli_server, tmp_path: Path):
    """Тест команды exec: успешное выполнение (0) и падение команды (4)."""
    _, port, _ = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    # 1. Успешный запуск команды
    res = runner.invoke(
        app,
        ["exec", "echo test-token-123", "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == ExitCode.SUCCESS
    data = json.loads(res.stdout)
    assert data["exit_code"] == 0
    assert "test-token-123" in data["stdout"]

    # 2. Ненулевой код возврата процесса -> ExitCode.COMMAND_FAILED (4)
    res_fail = runner.invoke(
        app,
        ["exec", "exit 42", "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res_fail.exit_code == ExitCode.COMMAND_FAILED
    data_fail = json.loads(res_fail.stdout)
    assert data_fail["exit_code"] == 42


def test_cli_pocket_commands(cli_server, tmp_path: Path):
    """Тест подкоманд pocket: status, push, pull, sync."""
    _, port, server_pocket = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    # pocket status
    res = runner.invoke(
        app,
        ["pocket", "status", "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == ExitCode.SUCCESS
    stat = json.loads(res.stdout)
    assert "local_files_count" in stat

    # pocket push
    local_file = local_pocket / "cli_sample.txt"
    local_file.write_text("CLI pocket push test", encoding="utf-8")
    res_push = runner.invoke(
        app,
        [
            "pocket",
            "push",
            str(local_file),
            "--port",
            str(port),
            "--config",
            str(cfg_file),
            "--json",
        ],
    )
    assert res_push.exit_code == ExitCode.SUCCESS
    assert (server_pocket / "cli_sample.txt").exists()

    # pocket pull
    (server_pocket / "server_asset.txt").write_text("remote asset", encoding="utf-8")
    dest_path = local_pocket / "downloaded_asset.txt"
    res_pull = runner.invoke(
        app,
        [
            "pocket",
            "pull",
            "server_asset.txt",
            "--dest",
            str(dest_path),
            "--port",
            str(port),
            "--config",
            str(cfg_file),
            "--json",
        ],
    )
    assert res_pull.exit_code == ExitCode.SUCCESS
    assert dest_path.exists()
    assert dest_path.read_text(encoding="utf-8") == "remote asset"

    # pocket sync
    res_sync = runner.invoke(
        app,
        [
            "pocket",
            "sync",
            "--direction",
            "both",
            "--port",
            str(port),
            "--config",
            str(cfg_file),
            "--json",
        ],
    )
    assert res_sync.exit_code == ExitCode.SUCCESS
    sync_data = json.loads(res_sync.stdout)
    assert len(sync_data["errors"]) == 0


def test_cli_notes_commands(cli_server, tmp_path: Path):
    """Тест подкоманд note: send, list, read."""
    _, port, _ = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    # note send
    res_send = runner.invoke(
        app,
        [
            "note",
            "send",
            "https://github.com/project",
            "--port",
            str(port),
            "--config",
            str(cfg_file),
            "--json",
        ],
    )
    assert res_send.exit_code == ExitCode.SUCCESS
    deliv = json.loads(res_send.stdout)
    note_id = deliv["note_id"]

    # note list
    res_list = runner.invoke(
        app,
        ["note", "list", "--limit", "10", "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res_list.exit_code == ExitCode.SUCCESS
    list_data = json.loads(res_list.stdout)
    assert any(n["note_id"] == note_id for n in list_data["notes"])

    # note read
    res_read = runner.invoke(
        app,
        ["note", "read", note_id, "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res_read.exit_code == ExitCode.SUCCESS
    read_data = json.loads(res_read.stdout)
    assert read_data["marked_count"] >= 1


def test_cli_network_error_exit_code(tmp_path: Path):
    """Проверяет exit code 2 (NETWORK_ERROR) при попытке подключения к недоступному порту."""
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    res = runner.invoke(
        app,
        ["ping", "--port", "59998", "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == ExitCode.NETWORK_ERROR
    data = json.loads(res.stdout)
    assert data["status"] == "error"
    assert data["error_code"] == 2
    assert data["error_type"] == "BridgeNetworkError"


def test_cli_auth_error_exit_code(cli_auth_server, tmp_path: Path):
    """Проверяет exit code 3 (AUTH_ERROR) при неверном токене."""
    _, port, _ = cli_auth_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()

    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(
        connection=ConnectionConfig(psk_token="WRONG_SECRET"),
        pocket=PocketConfig(path=str(local_pocket)),
    ).save(cfg_file)

    res = runner.invoke(
        app,
        ["exec", "echo test", "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == ExitCode.AUTH_ERROR
    data = json.loads(res.stdout)
    assert data["status"] == "error"
    assert data["error_code"] == 3
    assert data["error_type"] == "BridgeAuthError"


def test_cli_welcome_and_tui_single_pass():
    """Проверяет отрисовку welcome и TUI без зависания."""
    res_welcome = runner.invoke(app, ["welcome"])
    assert res_welcome.exit_code == 0
    assert "BRIDGES" in res_welcome.stdout

    res_tui = runner.invoke(app, ["tui", "--single-pass", "--mode", "DASH"])
    assert res_tui.exit_code == 0
    assert "DRAWBRIDGE" in res_tui.stdout


def test_cli_send_success(cli_server, tmp_path: Path):
    """Проверяет успешную прямую отправку файла через команду bridge-cli send."""
    _, port, srv_pocket = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    test_file = tmp_path / "quick_drop.txt"
    test_file.write_text("Hello via bridge-cli send!", encoding="utf-8")

    res = runner.invoke(
        app,
        ["send", str(test_file), "--port", str(port), "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["count"] == 1
    assert data["sent"][0]["file"] == "quick_drop.txt"
    assert data["sent"][0]["completed"] is True

    # Проверяем фактическое появление файла на стороне сервера
    received = srv_pocket / "quick_drop.txt"
    assert received.exists()
    assert received.read_text(encoding="utf-8") == "Hello via bridge-cli send!"


def test_cli_send_multiple_files(cli_server, tmp_path: Path):
    """Проверяет отправку нескольких файлов одной командой."""
    _, port, srv_pocket = cli_server
    local_pocket = tmp_path / "client_pocket"
    local_pocket.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(local_pocket))).save(cfg_file)

    f1 = tmp_path / "doc1.pdf"
    f2 = tmp_path / "doc2.png"
    f1.write_bytes(b"%PDF-1.4 dummy")
    f2.write_bytes(b"\x89PNG dummy")

    res = runner.invoke(
        app,
        ["send", str(f1), str(f2), "--port", str(port), "--config", str(cfg_file)],
    )
    assert res.exit_code == 0
    assert "Отправлен doc1.pdf" in res.stdout
    assert "Отправлен doc2.png" in res.stdout
    assert (srv_pocket / "doc1.pdf").exists()
    assert (srv_pocket / "doc2.png").exists()


def test_cli_send_nonexistent_file(tmp_path: Path):
    """Проверяет быструю валидацию отсутствующего файла без сетевого подключения (ExitCode 1)."""
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig().save(cfg_file)

    res = runner.invoke(
        app,
        ["send", str(tmp_path / "not_there.bin"), "--config", str(cfg_file), "--json"],
    )
    assert res.exit_code == ExitCode.GENERAL_ERROR
    data = json.loads(res.stdout)
    assert data["status"] == "error"
    assert data["error_code"] == 1
    assert "не найден" in data["message"]
