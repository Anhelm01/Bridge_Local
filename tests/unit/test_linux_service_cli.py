"""
Тесты для bridge_client_linux.cli — команды управления службой bridge-cli service (run/start/stop/status/systemd).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from bridge_client_linux.cli import (
    _check_port_listening,
    _get_service_pid_file,
    _is_pid_alive,
    app,
)

runner = CliRunner()


class TestLinuxServiceHelpers:
    """Тесты вспомогательных функций службы."""

    def test_get_service_pid_file(self, tmp_path: Path) -> None:
        pid_file = _get_service_pid_file(tmp_path)
        assert pid_file == tmp_path / ".bridge_service.pid"

    def test_check_port_listening_closed(self) -> None:
        # Несуществующий локальный порт (высокий)
        is_open = _check_port_listening("127.0.0.1", 59999, timeout_sec=0.1)
        assert is_open is False

    def test_is_pid_alive_invalid(self) -> None:
        assert _is_pid_alive(-1) is False
        assert _is_pid_alive(0) is False
        assert _is_pid_alive(99999999) is False


class TestLinuxServiceCommands:
    """Тесты CLI команд bridge-cli service."""

    def test_service_status_json_offline(self, tmp_path: Path) -> None:
        # Создаем временную конфигурацию
        cfg_path = tmp_path / "bridge.toml"
        cfg_path.write_text("""
[connection]
host = "127.0.0.1"
port = 58888
[pocket]
path = "pocket"
""")

        res = runner.invoke(app, ["service", "status", "--json", "-c", str(cfg_path)])
        assert res.exit_code == 0
        data = json.loads(res.stdout)
        assert data["running"] is False
        assert data["port"] == 58888
        assert data["port_listening"] is False
        assert data["pid_alive"] is False

    def test_service_stop_when_inactive(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "bridge.toml"
        cfg_path.write_text("""
[connection]
host = "127.0.0.1"
port = 58888
[pocket]
path = "pocket"
""")

        res = runner.invoke(app, ["service", "stop", "--json", "-c", str(cfg_path)])
        assert res.exit_code == 0
        data = json.loads(res.stdout)
        assert data["status"] == "stopped"
        assert data["killed"] is False

    def test_service_install_and_uninstall_systemd(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "bridge.toml"
        cfg_path.write_text("""
[connection]
host = "127.0.0.1"
port = 58888
""")

        with patch("shutil.which", return_value="/bin/systemctl"), \
             patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.home", return_value=tmp_path):

            mock_run.return_value = MagicMock(returncode=0, stderr="")

            # 1. install-systemd
            res_install = runner.invoke(app, ["service", "install-systemd", "--json", "-c", str(cfg_path)])
            assert res_install.exit_code == 0
            data_install = json.loads(res_install.stdout)
            assert data_install["status"] == "installed"
            assert data_install["enabled"] is True

            unit_file = tmp_path / ".config" / "systemd" / "user" / "bridge-local.service"
            assert unit_file.exists()
            assert "ExecStart=" in unit_file.read_text()

            # 2. uninstall-systemd
            res_uninstall = runner.invoke(app, ["service", "uninstall-systemd", "--json"])
            assert res_uninstall.exit_code == 0
            data_uninstall = json.loads(res_uninstall.stdout)
            assert data_uninstall["status"] == "uninstalled"
            assert not unit_file.exists()
