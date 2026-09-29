"""
bridge_core.models — Pydantic V2 DTO модели для всех сетевых сообщений Bridge Local.

Определяет типизированные контракты для:
  - JSON-RPC 2.0 обёртки (запрос, ответ, ошибка).
  - Heartbeat (Ping / Pong).
  - Удалённое выполнение команд (ExecRequest / ExecResponse).
  - Записки (NoteMessage / NoteDelivery).
  - Синхронизация «кармана» (PocketManifest / FileChunkRequest).
  - Аудит-лог (.jsonl строка).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Общие перечисления (Enums)
# ---------------------------------------------------------------------------


class NodeOS(StrEnum):
    """Операционная система узла."""

    LINUX = "linux"
    WINDOWS = "windows"


class NodeStatus(StrEnum):
    """Статус узла из heartbeat."""

    READY = "ready"
    BUSY = "busy"
    SHUTTING_DOWN = "shutting_down"


class ConnectionState(StrEnum):
    """Состояние подключения клиента к агенту."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    UNREACHABLE = "unreachable"


class AuditStatus(StrEnum):
    """Статус записи в аудит-логе."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class NoteStatus(StrEnum):
    """Статус доставки записки."""

    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Утилитарные функции
# ---------------------------------------------------------------------------


def _generate_id() -> str:
    """Генерирует уникальный идентификатор для RPC-запросов."""
    return str(uuid.uuid4())


def _now_us() -> int:
    """Текущее время в микросекундах (UTC epoch)."""
    return int(datetime.now(UTC).timestamp() * 1_000_000)


def _now_iso() -> str:
    """Текущее время в ISO-8601 UTC."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 обёртки
# ---------------------------------------------------------------------------


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 запрос с поддержкой маршрутизации мульти-нод."""

    jsonrpc: str = Field(default="2.0", frozen=True)
    method: str = Field(description="Имя метода RPC (например 'exec.run', 'heartbeat.ping')")
    id: str = Field(default_factory=_generate_id, description="Уникальный идентификатор запроса")
    params: dict[str, Any] = Field(default_factory=dict, description="Параметры метода")
    source_node: str | None = Field(
        default=None,
        description="Имя узла-отправителя (для мульти-узловой адресации F1/F2)",
    )
    target_node: str | None = Field(
        default=None,
        description="Имя целевого узла (для мульти-узловой адресации F1/F2)",
    )


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 успешный ответ."""

    jsonrpc: str = Field(default="2.0", frozen=True)
    id: str = Field(description="ID запроса, на который отвечаем")
    result: dict[str, Any] = Field(description="Результат выполнения метода")


class JsonRpcError(BaseModel):
    """Структура ошибки JSON-RPC 2.0."""

    code: int = Field(description="Код ошибки (< 0 для серверных)")
    message: str = Field(description="Человекочитаемое описание ошибки")
    data: dict[str, Any] | None = Field(default=None, description="Дополнительные данные об ошибке")


class JsonRpcErrorResponse(BaseModel):
    """JSON-RPC 2.0 ответ с ошибкой."""

    jsonrpc: str = Field(default="2.0", frozen=True)
    id: str = Field(description="ID запроса, на который отвечаем")
    error: JsonRpcError = Field(description="Объект ошибки")


# ---------------------------------------------------------------------------
# Стандартные коды ошибок JSON-RPC
# ---------------------------------------------------------------------------


class RpcErrorCode:
    """Стандартные + кастомные коды ошибок JSON-RPC."""

    # Стандартные JSON-RPC 2.0
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Кастомные Bridge Local
    COMMAND_TIMEOUT = -32001
    COMMAND_FAILED = -32002
    AUTH_FAILED = -32003
    NODE_UNREACHABLE = -32004
    POCKET_SYNC_ERROR = -32005
    FILE_NOT_FOUND = -32006


# ---------------------------------------------------------------------------
# Heartbeat (Ping / Pong)
# ---------------------------------------------------------------------------


class PingParams(BaseModel):
    """Параметры запроса heartbeat.ping."""

    client_timestamp_us: int = Field(
        default_factory=_now_us,
        description="Timestamp отправки в микросекундах (UTC epoch)",
    )
    client_os: NodeOS = Field(description="ОС клиента-отправителя")


class PongResult(BaseModel):
    """Результат ответа heartbeat.pong."""

    agent_timestamp_us: int = Field(
        default_factory=_now_us,
        description="Timestamp ответа агента в микросекундах (UTC epoch)",
    )
    agent_os: NodeOS = Field(description="ОС агента")
    cpu_percent: float = Field(ge=0.0, le=100.0, description="Загрузка CPU в процентах")
    memory_used_mb: int = Field(ge=0, description="Использование RAM в мегабайтах")
    uptime_seconds: int = Field(ge=0, description="Uptime системы в секундах")
    status: NodeStatus = Field(description="Текущий статус узла")


# ---------------------------------------------------------------------------
# Удалённое выполнение команд (Exec)
# ---------------------------------------------------------------------------


class ExecRequestParams(BaseModel):
    """Параметры запроса exec.run."""

    command: str = Field(min_length=1, description="Команда PowerShell для выполнения")
    timeout_sec: int = Field(
        default=30,
        gt=0,
        le=3600,
        description="Таймаут выполнения в секундах (1–3600)",
    )
    run_as_admin: bool = Field(
        default=True,
        description="Запускать с повышенными привилегиями (Administrator)",
    )
    working_dir: str | None = Field(
        default=None,
        description="Рабочий каталог для выполнения (None = по умолчанию агента)",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Дополнительные переменные окружения",
    )
    target_node: str | None = Field(
        default=None,
        description="Имя целевого узла (для будущей мульти-узловой адресации F1/F2)",
    )


class ExecResult(BaseModel):
    """Результат успешного выполнения команды."""

    exit_code: int = Field(description="Код возврата процесса")
    stdout: str = Field(default="", description="Стандартный вывод (UTF-8)")
    stderr: str = Field(default="", description="Стандартный вывод ошибок (UTF-8)")
    duration_ms: int = Field(ge=0, description="Длительность выполнения в миллисекундах")
    started_at: str = Field(description="ISO-8601 время начала выполнения")
    completed_at: str = Field(description="ISO-8601 время завершения")
    timed_out: bool = Field(default=False, description="Был ли достигнут таймаут")
    encoding_detected: str = Field(
        default="utf-8",
        description="Кодировка, обнаруженная в выводе процесса",
    )


class ExecTimeoutErrorData(BaseModel):
    """Дополнительные данные для ошибки таймаута выполнения."""

    timeout_sec: int = Field(description="Установленный лимит в секундах")
    duration_ms: int = Field(description="Фактическая длительность до завершения")
    partial_stdout: str = Field(default="", description="Частичный stdout до момента прерывания")
    processes_killed: list[int] = Field(
        default_factory=list,
        description="PID'ы завершённых процессов из дерева",
    )


# ---------------------------------------------------------------------------
# Записки (Notes)
# ---------------------------------------------------------------------------


class NoteSendParams(BaseModel):
    """Параметры отправки записки (notes.send)."""

    text: str = Field(min_length=1, max_length=10000, description="Текст записки")
    author_os: NodeOS = Field(description="ОС автора записки")
    target_node: str | None = Field(
        default=None,
        description="Имя узла-получателя (None = текущий узел / все)",
    )


class NoteDeliveryResult(BaseModel):
    """Результат доставки записки."""

    note_id: str = Field(description="Уникальный ID записки")
    received_at: str = Field(
        default_factory=_now_iso,
        description="ISO-8601 время получения",
    )
    status: NoteStatus = Field(default=NoteStatus.DELIVERED, description="Статус доставки")


class NoteHistoryParams(BaseModel):
    """Параметры запроса истории записок (notes.history)."""

    limit: int = Field(default=50, gt=0, le=500, description="Максимум записок в ответе")
    since: str | None = Field(
        default=None,
        description="ISO-8601 — показать записки начиная с этого времени",
    )


class NoteEntry(BaseModel):
    """Одна записка в истории."""

    note_id: str = Field(description="Уникальный ID записки")
    timestamp: str = Field(description="ISO-8601 время создания")
    author_os: NodeOS = Field(description="ОС автора")
    text: str = Field(description="Текст записки")
    status: NoteStatus = Field(description="Статус (delivered / read)")


class NoteHistoryResult(BaseModel):
    """Результат запроса истории записок."""

    notes: list[NoteEntry] = Field(default_factory=list, description="Список записок")
    total_count: int = Field(ge=0, description="Общее количество записок по фильтру")


class NoteMarkReadParams(BaseModel):
    """Параметры квитирования прочтения записок (notes.mark_read)."""

    note_ids: list[str] = Field(
        min_length=1, description="Список ID записок для отметки прочтёнными"
    )


class NoteMarkReadResult(BaseModel):
    """Результат квитирования прочтения записок."""

    marked_count: int = Field(ge=0, description="Количество успешно обновлённых записок")


# ---------------------------------------------------------------------------
# Синхронизация «Кармана» (Pocket Sync)
# ---------------------------------------------------------------------------


class PocketFileInfo(BaseModel):
    """Метаданные одного файла в кармане."""

    path: str = Field(description="Относительный путь файла (от корня кармана)")
    sha256: str = Field(min_length=64, max_length=64, description="SHA-256 хеш содержимого")
    size_bytes: int = Field(ge=0, description="Размер файла в байтах")
    mtime_iso: str = Field(description="ISO-8601 время последней модификации")


class PocketManifestResult(BaseModel):
    """Результат запроса манифеста кармана (pocket.manifest)."""

    files: list[PocketFileInfo] = Field(default_factory=list, description="Список файлов")
    total_size_bytes: int = Field(ge=0, description="Суммарный размер всех файлов")
    file_count: int = Field(ge=0, description="Количество файлов")


class PocketPullParams(BaseModel):
    """Параметры запроса чанка файла (pocket.pull)."""

    path: str = Field(min_length=1, description="Относительный путь файла")
    offset: int = Field(default=0, ge=0, description="Смещение в байтах от начала файла")
    chunk_size: int = Field(
        default=65536,
        gt=0,
        le=4_194_304,
        description="Размер запрашиваемого чанка (макс. 4 МБ)",
    )


class PocketPushParams(BaseModel):
    """Параметры отправки чанка файла (pocket.push)."""

    path: str = Field(min_length=1, description="Относительный путь файла в кармане")
    offset: int = Field(ge=0, description="Смещение в байтах")
    data_b64: str = Field(description="Base64-закодированные данные чанка")
    is_last: bool = Field(default=False, description="Последний ли чанк файла")
    sha256_full: str | None = Field(
        default=None,
        description="SHA-256 полного файла (передаётся с последним чанком для верификации)",
    )


class PocketPullResult(BaseModel):
    """Результат запроса чанка файла (pocket.pull)."""

    path: str = Field(description="Относительный путь файла")
    offset: int = Field(ge=0, description="Смещение чанка в байтах")
    data_b64: str = Field(description="Base64-закодированные данные чанка")
    is_last: bool = Field(description="Является ли чанк завершающим для файла")
    total_size_bytes: int = Field(ge=0, description="Полный размер файла в байтах")


class PocketPushResult(BaseModel):
    """Результат отправки чанка файла (pocket.push)."""

    path: str = Field(description="Относительный путь файла")
    offset: int = Field(ge=0, description="Смещение записанного чанка")
    bytes_written: int = Field(ge=0, description="Количество байт, записанных в этом чанке")
    is_last: bool = Field(description="Является ли чанк завершающим")
    completed: bool = Field(description="Завершена ли сборка файла целиком")
    sha256: str | None = Field(
        default=None,
        description="SHA-256 хеш файла при completed=True (после успешной валидации)",
    )


# ---------------------------------------------------------------------------
# Аудит-лог (JSONL запись в pocket/logs/YYYY-MM-DD.jsonl)
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    """
    Одна строка аудит-лога в формате JSONL.

    Каждая запись — самодостаточный JSON-объект с полной информацией
    о выполненном запросе и его результате.
    """

    ts: str = Field(
        default_factory=_now_iso,
        description="ISO-8601 timestamp события (UTC)",
    )
    session_id: str = Field(description="Идентификатор текущей сессии подключения")
    client_ip: str = Field(description="IP-адрес клиента, инициировавшего запрос")
    method: str = Field(description="RPC-метод (exec.run, notes.send, pocket.pull, ...)")
    request_id: str = Field(description="Уникальный ID запроса (совпадает с JSON-RPC id)")
    command: str | None = Field(
        default=None,
        description="Команда PowerShell (только для exec.run)",
    )
    timeout_sec: int | None = Field(
        default=None,
        description="Установленный таймаут (только для exec.run)",
    )
    exit_code: int | None = Field(
        default=None,
        description="Код возврата (только для exec.run)",
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Длительность обработки запроса в мс",
    )
    stdout_preview: str = Field(
        default="",
        max_length=1000,
        description="Первые 1000 символов stdout (только для exec.run)",
    )
    stderr_preview: str = Field(
        default="",
        max_length=1000,
        description="Первые 1000 символов stderr (только для exec.run)",
    )
    timed_out: bool = Field(default=False, description="Был ли таймаут")
    status: AuditStatus = Field(description="Итоговый статус операции")


# ---------------------------------------------------------------------------
# Wire Protocol — фрейм (для сериализации/десериализации на транспортном уровне)
# ---------------------------------------------------------------------------

# Магические байты для идентификации фрейма Bridge Local
FRAME_MAGIC = b"\x42\x52"  # "BR"
FRAME_MAGIC_INT = 0x4252

# Максимальный размер payload (64 МБ по умолчанию)
MAX_PAYLOAD_SIZE = 64 * 1024 * 1024

# Длина заголовка фрейма: MAGIC (2) + LEN (4) = 6 байт
FRAME_HEADER_SIZE = 6


# ---------------------------------------------------------------------------
# Реестр RPC-методов (для маршрутизации)
# ---------------------------------------------------------------------------


class RpcMethod:
    """Константы имён RPC-методов для единообразного использования."""

    HEARTBEAT_PING = "heartbeat.ping"
    EXEC_RUN = "exec.run"
    NOTES_SEND = "notes.send"
    NOTES_HISTORY = "notes.history"
    NOTES_MARK_READ = "notes.mark_read"
    POCKET_MANIFEST = "pocket.manifest"
    POCKET_PULL = "pocket.pull"
    POCKET_PUSH = "pocket.push"
