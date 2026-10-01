"""
bridge_core.config — Конфигурация Bridge Local (TOML).

Загрузка, валидация и сохранение конфигурации из bridge.toml.
Использует встроенный tomllib (Python 3.11+) для парсинга и
tomli_w-совместимую запись через ручной сериализатор.
"""

from __future__ import annotations

import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Путь к конфигу по умолчанию (рядом с точкой запуска)
DEFAULT_CONFIG_PATH = Path("bridge.toml")


class ConnectionConfig(BaseModel):
    """Настройки сетевого подключения."""

    host: str = Field(
        default="0.0.0.0",
        description="IP-адрес или hostname удалённого узла (для клиента) / bind-адрес (для агента)",
    )
    port: int = Field(
        default=9732,
        description="TCP-порт для подключения (0 = динамический порт ОС, 1024..65535)",
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v != 0 and not (1024 <= v <= 65535):
            raise ValueError("Порт должен быть 0 (динамический) или в диапазоне 1024..65535")
        return v

    timeout_sec: float = Field(
        default=5.0,
        gt=0,
        description="Таймаут подключения к узлу (секунды)",
    )
    tls_cert_path: str | None = Field(
        default=None,
        description="Путь к TLS-сертификату (PEM)",
    )
    tls_key_path: str | None = Field(
        default=None,
        description="Путь к приватному ключу TLS (PEM)",
    )
    psk_token: str | None = Field(
        default=None,
        description="Pre-shared key для аутентификации",
    )


class HeartbeatConfig(BaseModel):
    """Настройки heartbeat-механизма."""

    interval_sec: float = Field(
        default=2.0,
        gt=0,
        description="Интервал отправки ping (секунды)",
    )
    timeout_sec: float = Field(
        default=1.5,
        gt=0,
        description="Таймаут ожидания pong (секунды). Fail-fast порог.",
    )
    max_missed: int = Field(
        default=3,
        ge=1,
        description="Количество пропущенных pong до перехода в UNREACHABLE",
    )
    reconnect_delay_sec: float = Field(
        default=5.0,
        gt=0,
        description="Задержка перед попыткой реконнекта (секунды)",
    )


class PocketConfig(BaseModel):
    """Настройки общей папки «карман»."""

    path: str = Field(
        default="./pocket",
        description="Путь к каталогу кармана",
    )
    logs_subdir: str = Field(
        default="logs",
        description="Имя подкаталога для аудит-логов внутри кармана",
    )
    sync_watch: bool = Field(
        default=True,
        description="Включить автоматический watchdog (inotify / ReadDirectoryChanges)",
    )
    max_chunk_size: int = Field(
        default=65536,
        gt=0,
        le=4_194_304,
        description="Максимальный размер чанка при передаче файлов (байт)",
    )
    log_max_days: int = Field(
        default=30,
        ge=1,
        description="Хранить лог-файлы не старше N дней",
    )


class ExecConfig(BaseModel):
    """Настройки удалённого выполнения команд."""

    default_timeout_sec: int = Field(
        default=30,
        gt=0,
        le=3600,
        description="Таймаут по умолчанию для выполнения команды (секунды)",
    )
    run_as_admin: bool = Field(
        default=True,
        description="Запускать PowerShell с повышенными привилегиями по умолчанию",
    )
    force_utf8: bool = Field(
        default=True,
        description="Принудительно устанавливать UTF-8 кодировку (chcp 65001)",
    )


class LoggingConfig(BaseModel):
    """Настройки системы логирования."""

    level: str = Field(
        default="TRACE",
        description="Уровень логирования: TRACE, DEBUG, INFO, WARNING, ERROR",
    )
    dev_mode: bool = Field(
        default=True,
        description="Включить Dev-Mode Hyper-Logging (подробная трассировка всех уровней)",
    )
    console_output: bool = Field(
        default=True,
        description="Выводить логи в консоль",
    )
    file_output: str | None = Field(
        default=None,
        description="Путь к файлу для записи логов (None = только консоль)",
    )


class NodeConfig(BaseModel):
    """Идентификация текущего узла (для мульти-узловой сети F1 и межагентного моста F2)."""

    name: str = Field(
        default="local-node",
        description="Человекочитаемое имя текущего узла (например workstation-lin, win-rig)",
    )
    display_name: str | None = Field(
        default=None,
        description="Понятное отображаемое имя для человека",
    )


class BridgeConfig(BaseModel):
    """
    Корневая конфигурация Bridge Local.

    Загружается из bridge.toml и валидируется через Pydantic.
    """

    node: NodeConfig = Field(default_factory=NodeConfig)
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    pocket: PocketConfig = Field(default_factory=PocketConfig)
    exec: ExecConfig = Field(default_factory=ExecConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Путь к файлу конфига, из которого загрузили (не сериализуется)
    _config_path: ClassVar[Path | None] = None

    @classmethod
    def load(cls, path: Path | None = None) -> BridgeConfig:
        """
        Загрузить конфиг из TOML файла.

        Args:
            path: Путь к bridge.toml. Если None — ищет в текущей директории.

        Returns:
            BridgeConfig с загруженными значениями (или значениями по умолчанию).
        """
        config_path = path
        if config_path is None:
            env_override = os.environ.get("BRIDGE_CONFIG")
            if env_override:
                config_path = Path(env_override)

        if config_path is None:
            candidate_paths: list[Path] = [
                DEFAULT_CONFIG_PATH,
                Path(sys.executable).parent / "bridge.toml",
            ]
            if sys.platform == "win32":
                candidate_paths.append(Path(r"C:\BridgeLocal\bridge.toml"))
            else:
                candidate_paths.append(Path.home() / ".config" / "bridge-local" / "bridge.toml")

            # Поддержка распакованного бандла PyInstaller (_MEIPASS)
            if hasattr(sys, "_MEIPASS"):
                candidate_paths.append(Path(sys._MEIPASS) / "bridge.toml")

            for cand in candidate_paths:
                if cand.exists():
                    config_path = cand
                    break

        config_path = config_path or (
            Path(sys.executable).parent / "bridge.toml"
            if sys.platform == "win32"
            else DEFAULT_CONFIG_PATH
        )

        if not config_path.exists():
            logger.info(
                "Файл конфигурации не найден: %s — используются значения по умолчанию",
                config_path,
            )
            config = cls()
            cls._config_path = config_path
            return config

        logger.debug("Загрузка конфигурации из: %s", config_path)
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)

        config = cls.model_validate(raw)
        cls._config_path = config_path
        logger.info("Конфигурация загружена из: %s", config_path)
        return config

    def get_pocket_dir(self) -> Path:
        """
        Возвращает абсолютный путь к каталогу кармана.

        Если в bridge.toml указан относительный путь (например, './pocket'),
        он разрешается относительно каталога самого bridge.toml.
        """
        p = Path(self.pocket.path).expanduser()
        if not p.is_absolute() and self._config_path:
            return (self._config_path.parent / p).resolve()
        return p.resolve()

    def to_toml_string(self) -> str:
        """
        Сериализовать конфиг в TOML-строку.

        Не использует внешних зависимостей — простой ручной сериализатор
        достаточен для плоских моделей Pydantic.
        """
        lines: list[str] = []
        data = self.model_dump()
        for section_name, section_data in data.items():
            lines.append(f"[{section_name}]")
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    lines.append(f"{key} = {_toml_value(value)}")
            lines.append("")
        return "\n".join(lines)

    def save(self, path: Path | None = None) -> None:
        """Сохранить конфиг в TOML файл."""
        save_path = path or self._config_path or DEFAULT_CONFIG_PATH
        content = self.to_toml_string()
        save_path.write_text(content, encoding="utf-8")
        logger.info("Конфигурация сохранена в: %s", save_path)


def _toml_value(value: object) -> str:
    """Форматирует Python-значение в TOML-совместимую строку."""
    if value is None:
        return '""'  # TOML не имеет null — используем пустую строку
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        # Экранирование кавычек
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{value}"'
