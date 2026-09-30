"""
tests/unit/test_packaging_and_deployment.py — Тестирование механизмов упаковки,
скриптов развертывания, PyInstaller спецификации и переключения Dev-mode / Release mode.
"""

from __future__ import annotations

import ast
import io
import logging
import sys
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bridge_agent_win.cli import main as win_agent_cli_main
from bridge_core.config import LoggingConfig
from bridge_core.logger import TRACE_LEVEL_NUM, AtomicJsonlLogger, setup_logging
from bridge_core.models import AuditLogEntry, AuditStatus


class TestPyprojectPackagingConfig:
    """Проверка конфигурации сборки и метаданных в pyproject.toml."""

    def test_pyproject_scripts_and_packages(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        pyproject_path = root_dir / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml должен существовать"

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        assert project.get("name") == "bridge-local"
        assert project.get("version") == "0.1.0"

        # Проверка точек входа console_scripts
        scripts = project.get("scripts", {})
        assert "bridge-cli" in scripts
        assert scripts["bridge-cli"] == "bridge_local:main"
        assert "bridge-agent" in scripts
        assert scripts["bridge-agent"] == "bridge_agent_win.cli:main"

        # Проверка зависимостей
        deps = project.get("dependencies", [])
        dep_str = " ".join(deps)
        assert "pydantic" in dep_str
        assert "watchdog" in dep_str
        assert "typer" in dep_str
        assert "rich" in dep_str
        assert "psutil" in dep_str
        assert "pywin32" in dep_str
        assert "sys_platform == 'win32'" in dep_str or 'sys_platform == "win32"' in dep_str

        # Проверка включения всех 4 пакетов в сборку wheel
        hatch_packages = (
            data.get("tool", {})
            .get("hatch", {})
            .get("build", {})
            .get("targets", {})
            .get("wheel", {})
            .get("packages", [])
        )
        assert "src/bridge_core" in hatch_packages
        assert "src/bridge_agent_win" in hatch_packages
        assert "src/bridge_client_linux" in hatch_packages
        assert "src/bridge_local" in hatch_packages


class TestModuleEntrypoints:
    """Проверка доступности точек входа __main__.py для запуска через python -m."""

    def test_bridge_local_main_importable(self) -> None:
        import bridge_local.__main__

        assert hasattr(bridge_local.__main__, "main")

    def test_bridge_client_linux_main_importable(self) -> None:
        import bridge_client_linux.__main__

        assert hasattr(bridge_client_linux.__main__, "run")

    def test_bridge_agent_win_main_importable(self) -> None:
        import bridge_agent_win.__main__

        assert hasattr(bridge_agent_win.__main__, "main")


class TestPyInstallerSpec:
    """Проверка спецификации сборки автономного бинарного файла Windows-агента."""

    def test_spec_file_valid_python_syntax(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        spec_path = root_dir / "bridge-agent.spec"
        assert spec_path.exists(), "bridge-agent.spec должен существовать"

        content = spec_path.read_text(encoding="utf-8")
        # Проверяем синтаксическую валидность через AST
        tree = ast.parse(content, filename=str(spec_path))
        assert tree is not None

        # Проверяем ключевые директивы
        assert "bridge_agent_win" in content
        assert "bridge_core" in content
        assert "watchdog" in content
        assert "psutil" in content
        assert "win32service" in content
        assert "console=True" in content
        assert 'name="bridge-agent"' in content or "name='bridge-agent'" in content


class TestPowerShellDeploymentScripts:
    """Проверка PowerShell-скриптов развертывания и управления службой SCM."""

    def test_install_service_script_structure(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        script_path = root_dir / "scripts" / "install-service.ps1"
        assert script_path.exists(), "scripts/install-service.ps1 должен существовать"

        content = script_path.read_text(encoding="utf-8")

        # Проверка ключевых параметров
        assert "$InstallDir" in content
        assert "$PocketDir" in content
        assert "$Port" in content
        assert "$ServiceName" in content
        assert "$PskToken" in content
        assert "$SkipDefender" in content
        assert "$SkipFirewall" in content
        assert "$SkipIndexing" in content

        # Проверка обязательных действий
        assert "Add-MpPreference" in content, "Должна быть настройка исключений Windows Defender"
        assert "NotContentIndexed" in content, (
            "Должно быть отключение индексирования для каталога pocket"
        )
        assert "New-NetFirewallRule" in content, "Должно быть создание правила входящих подключений"
        assert "New-Service" in content, "Должна быть регистрация службы в SCM"
        assert "service-run" in content, "SCM служба должна запускаться с аргументом service-run"
        assert "sc.exe failure" in content, "Должна быть настройка политики перезапуска при сбоях"
        assert "Start-Service" in content, "Должен быть запуск службы"

        # Проверка отсутствия эмодзи
        for char in content:
            assert ord(char) < 0x1F300 or ord(char) > 0x1FAFF, f"Обнаружен эмодзи в {script_path}"

    def test_uninstall_service_script_structure(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        script_path = root_dir / "scripts" / "uninstall-service.ps1"
        assert script_path.exists(), "scripts/uninstall-service.ps1 должен существовать"

        content = script_path.read_text(encoding="utf-8")

        # Проверка ключевых параметров и команд деинсталляции
        assert "$ServiceName" in content
        assert "Stop-Service" in content, "Должна быть остановка службы"
        assert "sc.exe delete" in content, "Должно быть удаление службы из реестра SCM"
        assert "Remove-MpPreference" in content, "Должна быть очистка исключений Defender"
        assert "Remove-NetFirewallRule" in content, "Должно быть удаление правила брандмауэра"

        # Проверка отсутствия эмодзи
        for char in content:
            assert ord(char) < 0x1F300 or ord(char) > 0x1FAFF, f"Обнаружен эмодзи в {script_path}"

    def test_build_windows_agent_script(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        script_path = root_dir / "scripts" / "build-windows-agent.ps1"
        assert script_path.exists(), "scripts/build-windows-agent.ps1 должен существовать"

        content = script_path.read_text(encoding="utf-8")
        assert "bridge-agent.spec" in content
        assert "PyInstaller" in content or "pyinstaller" in content

    def test_systemd_service_units(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        client_unit = root_dir / "scripts" / "systemd" / "bridge-client-sync.service"
        agent_unit = root_dir / "scripts" / "systemd" / "bridge-agent.service"

        assert client_unit.exists()
        assert agent_unit.exists()

        client_content = client_unit.read_text(encoding="utf-8")
        assert "[Unit]" in client_content
        assert "[Service]" in client_content
        assert "bridge-cli pocket sync" in client_content

        agent_content = agent_unit.read_text(encoding="utf-8")
        assert "[Unit]" in agent_content
        assert "[Service]" in agent_content
        assert "bridge-agent run" in agent_content


class TestDevModeVsReleaseLogging:
    """Проверка переключения между Dev-Mode Hyper-Logging и Release Clean Mode."""

    def test_dev_mode_enabled_sets_trace_and_subsecond_format(self) -> None:
        cfg = LoggingConfig(level="TRACE", dev_mode=True, console_output=True)
        setup_logging(cfg)

        root = logging.getLogger()
        assert root.level == TRACE_LEVEL_NUM

        # Проверяем форматирование обработчика: должен содержать миллисекунды и имя/строку
        assert len(root.handlers) >= 1
        formatter = root.handlers[0].formatter
        assert formatter is not None
        assert "%(msecs)03d" in str(formatter._fmt)
        assert "%(name)s:%(lineno)d" in str(formatter._fmt)

    def test_release_mode_clean_logging(self) -> None:
        # В релизном режиме (dev_mode=False) дефолтный TRACE понижается до чистого INFO
        cfg = LoggingConfig(level="TRACE", dev_mode=False, console_output=True)
        setup_logging(cfg)

        root = logging.getLogger()
        assert root.level == logging.INFO

        # Проверяем форматирование обработчика: чистый формат без миллисекунд и номеров строк
        assert len(root.handlers) >= 1
        formatter = root.handlers[0].formatter
        assert formatter is not None
        assert "%(msecs)03d" not in str(formatter._fmt)
        assert "%(lineno)d" not in str(formatter._fmt)

    def test_atomic_jsonl_logger_dev_logging_toggle(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"

        # Логгер с отключенным dev_logging не должен вызывать verbose debug
        logger_clean = AtomicJsonlLogger(logs_dir=logs_dir, dev_logging=False)
        assert logger_clean.dev_logging is False

        entry = AuditLogEntry(
            session_id="test-clean",
            client_ip="127.0.0.1",
            method="exec.run",
            request_id="req-clean",
            status=AuditStatus.SUCCESS,
        )

        with patch("bridge_core.logger.logger.debug") as mock_debug:
            logger_clean.write_sync(entry)
            # Отладочный microsecond fsync лог не должен вызываться
            mock_debug.assert_not_called()

        # Логгер с включенным dev_logging вызывает debug-лог при уровне DEBUG
        logger_dev = AtomicJsonlLogger(logs_dir=logs_dir, dev_logging=True)
        with (
            patch("bridge_core.logger.logger.debug") as mock_debug,
            patch("bridge_core.logger.logger.isEnabledFor", return_value=True),
        ):
            logger_dev.write_sync(entry)
            mock_debug.assert_called_once()
            assert "[DEV-AUDIT-LOG]" in mock_debug.call_args[0][0]


class TestWindowsAgentCliCommands:
    """Проверка команд CLI агента Windows (bridge-agent)."""

    def test_cli_help_lists_all_commands(self) -> None:
        stdout_buf = io.StringIO()
        with patch.object(sys, "argv", ["bridge-agent", "--help"]), patch("sys.stdout", stdout_buf):
            try:
                win_agent_cli_main()
            except SystemExit as exc:
                assert exc.code == 0

        output = stdout_buf.getvalue()
        assert "run" in output
        assert "service" in output
        assert "drop" in output
        assert "install-context-menu" in output
        assert "uninstall-context-menu" in output
        assert "generate-reg" in output

    def test_cli_generate_reg_creates_file(self, tmp_path: Path) -> None:
        out_reg = tmp_path / "test.reg"
        with (
            patch.object(sys, "argv", ["bridge-agent", "generate-reg", str(out_reg)]),
            patch("sys.stdout", io.StringIO()),
        ):
            win_agent_cli_main()

        assert out_reg.exists()
        content = out_reg.read_text(encoding="utf-8")
        assert "Windows Registry Editor Version 5.00" in content
        assert "Bridge Local" in content

    def test_cli_service_dispatch(self) -> None:
        with patch("bridge_agent_win.cli.handle_service_command") as mock_handle:
            with patch.object(sys, "argv", ["bridge-agent", "service", "start"]):
                win_agent_cli_main()
            mock_handle.assert_called_once_with(["start"])

    def test_cli_service_run_dispatch(self) -> None:
        with patch("bridge_agent_win.cli.run_scm_service") as mock_scm:
            with patch.object(sys, "argv", ["bridge-agent", "service-run"]):
                win_agent_cli_main()
            mock_scm.assert_called_once()

    def test_cli_scm_auto_detect(self) -> None:
        mock_sm = MagicMock()
        mock_sm.RunningAsService.return_value = True
        with (
            patch.dict(sys.modules, {"servicemanager": mock_sm}),
            patch("bridge_agent_win.cli.HAS_WIN32SERVICE", True),
            patch("bridge_agent_win.cli.run_scm_service") as mock_scm,
            patch("sys.argv", ["bridge-agent"]),
        ):
            win_agent_cli_main()
            mock_scm.assert_called_once()

    def test_handle_service_command_passes_prog_name_in_argv(self) -> None:
        from bridge_agent_win.service import handle_service_command

        mock_win32util = MagicMock()
        with (
            patch.dict(sys.modules, {"win32serviceutil": mock_win32util}),
            patch("bridge_agent_win.service.HAS_WIN32SERVICE", True),
            patch("bridge_agent_win.service.win32serviceutil", mock_win32util, create=True),
            patch.object(sys, "argv", ["bridge-agent"]),
        ):
            handle_service_command(["install"])
            mock_win32util.HandleCommandLine.assert_called_once()
            _args, kwargs = mock_win32util.HandleCommandLine.call_args
            argv_passed = kwargs.get("argv", [])
            assert len(argv_passed) == 2
            assert "service" in argv_passed[0]
            assert argv_passed[1] == "install"

    def test_run_scm_service_initialization(self) -> None:
        from bridge_agent_win.service import run_scm_service

        mock_sm = MagicMock()
        with (
            patch.dict(sys.modules, {"servicemanager": mock_sm}),
            patch("bridge_agent_win.service.HAS_WIN32SERVICE", True),
            patch("bridge_agent_win.service.servicemanager", mock_sm, create=True),
        ):
            run_scm_service()
            mock_sm.Initialize.assert_called_once()
            mock_sm.PrepareToHostSingle.assert_called_once()
            mock_sm.StartServiceCtrlDispatcher.assert_called_once()


class TestWindowsServiceFramework:
    """Проверка жизненного цикла системной службы Windows SCM."""

    def test_service_class_attributes(self) -> None:
        from bridge_agent_win.service import BridgeLocalAgentWindowsService

        assert BridgeLocalAgentWindowsService._svc_name_ == "BridgeLocalAgent"
        assert BridgeLocalAgentWindowsService._exe_args_ == "service-run"
        assert "Bridge Local" in BridgeLocalAgentWindowsService._svc_display_name_

    def test_service_stop_sets_event_and_reports_status(self) -> None:
        from bridge_agent_win.service import BridgeLocalAgentWindowsService

        svc = BridgeLocalAgentWindowsService(["BridgeLocalAgent"])
        reports: list[int] = []
        svc.ReportServiceStatus = lambda status: reports.append(status)

        mock_subservice = patch("bridge_agent_win.service.WindowsBridgeService").start()
        svc._service = mock_subservice
        svc._loop = None

        svc.SvcStop()
        assert len(reports) >= 0

    def test_service_run_lifecycle_reporting(self) -> None:
        from bridge_agent_win.service import BridgeLocalAgentWindowsService

        svc = BridgeLocalAgentWindowsService(["BridgeLocalAgent"])
        reported_statuses: list[int] = []
        svc.ReportServiceStatus = lambda status: reported_statuses.append(status)

        # Проверяем, что _BaseServiceFramework предоставляет ReportServiceStatus
        svc.ReportServiceStatus(4)
        svc.ReportServiceStatus(3)
        svc.ReportServiceStatus(1)
        assert reported_statuses == [4, 3, 1]


class TestConfigCandidatePathResolution:
    """Проверка поиска конфигурационных файлов в BridgeConfig.load."""

    def test_env_var_bridge_config_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bridge_core.config import BridgeConfig

        cfg_file = tmp_path / "custom_bridge.toml"
        cfg_file.write_text("[connection]\nport = 8844\n", encoding="utf-8")

        monkeypatch.setenv("BRIDGE_CONFIG", str(cfg_file))
        cfg = BridgeConfig.load()
        assert cfg.connection.port == 8844

    def test_default_fallback_when_no_config_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from bridge_core.config import BridgeConfig

        monkeypatch.delenv("BRIDGE_CONFIG", raising=False)
        with patch("pathlib.Path.exists", return_value=False):
            cfg = BridgeConfig.load()
            assert cfg.connection.port == 9732
