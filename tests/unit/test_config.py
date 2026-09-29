"""
Тесты для bridge_core.config — загрузка, валидация и сериализация TOML-конфига.

Покрывает:
  - Загрузку из TOML файла.
  - Значения по умолчанию при отсутствии файла.
  - Roundtrip: load → save → load.
  - Валидацию ограничений полей.
  - TOML-сериализацию.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    ExecConfig,
    HeartbeatConfig,
    LoggingConfig,
    NodeConfig,
    PocketConfig,
)


class TestConnectionConfig:
    """Тесты настроек подключения."""

    def test_defaults(self) -> None:
        cfg = ConnectionConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9732
        assert cfg.timeout_sec == 5.0
        assert cfg.tls_cert_path is None
        assert cfg.psk_token is None

    def test_port_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionConfig(port=80)  # < 1024
        with pytest.raises(ValidationError):
            ConnectionConfig(port=70000)  # > 65535

    def test_custom_values(self) -> None:
        cfg = ConnectionConfig(host="192.168.1.50", port=8080, psk_token="my-secret")
        assert cfg.host == "192.168.1.50"
        assert cfg.psk_token == "my-secret"


class TestHeartbeatConfig:
    """Тесты настроек heartbeat."""

    def test_defaults(self) -> None:
        cfg = HeartbeatConfig()
        assert cfg.interval_sec == 2.0
        assert cfg.timeout_sec == 1.5
        assert cfg.max_missed == 3
        assert cfg.reconnect_delay_sec == 5.0

    def test_validation(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatConfig(max_missed=0)  # < 1


class TestPocketConfig:
    """Тесты настроек кармана."""

    def test_defaults(self) -> None:
        cfg = PocketConfig()
        assert cfg.path == "./pocket"
        assert cfg.logs_subdir == "logs"
        assert cfg.sync_watch is True
        assert cfg.max_chunk_size == 65536
        assert cfg.log_max_days == 30

    def test_chunk_size_bounds(self) -> None:
        with pytest.raises(ValidationError):
            PocketConfig(max_chunk_size=5_000_000)  # > 4MB


class TestExecConfig:
    """Тесты настроек выполнения."""

    def test_defaults(self) -> None:
        cfg = ExecConfig()
        assert cfg.default_timeout_sec == 30
        assert cfg.run_as_admin is True
        assert cfg.force_utf8 is True


class TestLoggingConfig:
    """Тесты настроек логирования."""

    def test_defaults(self) -> None:
        cfg = LoggingConfig()
        assert cfg.level == "TRACE"
        assert cfg.dev_mode is True
        assert cfg.console_output is True
        assert cfg.file_output is None


class TestNodeConfig:
    """Тесты настроек узла (мульти-ноды F1/F2)."""

    def test_defaults(self) -> None:
        cfg = NodeConfig()
        assert cfg.name == "local-node"
        assert cfg.display_name is None

    def test_custom(self) -> None:
        cfg = NodeConfig(name="workstation-lin", display_name="Рабочий ПК")
        assert cfg.name == "workstation-lin"
        assert cfg.display_name == "Рабочий ПК"


class TestBridgeConfig:
    """Тесты корневой конфигурации."""

    def test_all_defaults(self) -> None:
        cfg = BridgeConfig()
        assert cfg.node.name == "local-node"
        assert cfg.connection.port == 9732
        assert cfg.heartbeat.interval_sec == 2.0
        assert cfg.pocket.path == "./pocket"
        assert cfg.exec.default_timeout_sec == 30
        assert cfg.logging.dev_mode is True

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = BridgeConfig.load(tmp_path / "nonexistent.toml")
        assert cfg.connection.port == 9732

    def test_load_from_toml(self, tmp_path: Path) -> None:
        toml_content = """\
[connection]
host = "10.0.0.1"
port = 5555
timeout_sec = 10.0

[heartbeat]
interval_sec = 1.0
timeout_sec = 0.5
max_missed = 5

[pocket]
path = "/data/shared"
sync_watch = false

[exec]
default_timeout_sec = 60
run_as_admin = false

[logging]
level = "INFO"
dev_mode = false
"""
        config_file = tmp_path / "bridge.toml"
        config_file.write_text(toml_content, encoding="utf-8")

        cfg = BridgeConfig.load(config_file)
        assert cfg.connection.host == "10.0.0.1"
        assert cfg.connection.port == 5555
        assert cfg.heartbeat.max_missed == 5
        assert cfg.pocket.path == "/data/shared"
        assert cfg.pocket.sync_watch is False
        assert cfg.exec.run_as_admin is False
        assert cfg.logging.dev_mode is False

    def test_to_toml_string(self) -> None:
        cfg = BridgeConfig()
        toml_str = cfg.to_toml_string()
        assert "[connection]" in toml_str
        assert "[heartbeat]" in toml_str
        assert "[pocket]" in toml_str
        assert "[exec]" in toml_str
        assert "[logging]" in toml_str
        assert "port = 9732" in toml_str

    def test_save_and_reload(self, tmp_path: Path) -> None:
        """Roundtrip: создать конфиг → сохранить → загрузить → проверить."""
        original = BridgeConfig(
            connection=ConnectionConfig(host="1.2.3.4", port=4444, psk_token="secret123"),
            heartbeat=HeartbeatConfig(interval_sec=3.0),
            pocket=PocketConfig(path="/tmp/test_pocket"),
        )

        save_path = tmp_path / "bridge_roundtrip.toml"
        original.save(save_path)

        reloaded = BridgeConfig.load(save_path)
        assert reloaded.connection.host == "1.2.3.4"
        assert reloaded.connection.port == 4444
        assert reloaded.connection.psk_token == "secret123"
        assert reloaded.heartbeat.interval_sec == 3.0
        assert reloaded.pocket.path == "/tmp/test_pocket"

    def test_partial_toml_fills_defaults(self, tmp_path: Path) -> None:
        """Частичный TOML: указаны только некоторые секции, остальные — по умолчанию."""
        toml_content = """\
[connection]
port = 7777
"""
        config_file = tmp_path / "partial.toml"
        config_file.write_text(toml_content, encoding="utf-8")

        cfg = BridgeConfig.load(config_file)
        assert cfg.connection.port == 7777
        assert cfg.connection.host == "0.0.0.0"  # default
        assert cfg.heartbeat.interval_sec == 2.0  # default
        assert cfg.pocket.path == "./pocket"  # default
