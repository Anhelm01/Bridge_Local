"""
Bridge Core — общее ядро системы Bridge Local.

Экспортирует:
  - Сетевые протоколы и транспорт (AsyncTransportClient, AsyncTransportServer).
  - DTO-модели данных (Pydantic V2) для RPC-сообщений и аудита.
  - Движок структурированного логирования (AtomicJsonlLogger, setup_logging).
  - Механизм Fail-Fast Heartbeat (HeartbeatManager).
  - Декодер кодовых страниц Windows (WindowsOutputDecoder).
  - Модуль безопасности (PSKAuthenticator, validate_safe_path, SSL-контексты).
  - Конфигурацию TOML (BridgeConfig).
"""

from bridge_core.codec import DecodedOutput, WindowsOutputDecoder
from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    ExecConfig,
    HeartbeatConfig,
    LoggingConfig,
    NodeConfig,
    PocketConfig,
)
from bridge_core.heartbeat import HeartbeatManager, HeartbeatTimeoutError
from bridge_core.logger import AtomicJsonlLogger, setup_logging
from bridge_core.models import (
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    MAX_PAYLOAD_SIZE,
    AuditLogEntry,
    AuditStatus,
    ConnectionState,
    ExecRequestParams,
    ExecResult,
    ExecTimeoutErrorData,
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    NodeOS,
    NodeStatus,
    NoteDeliveryResult,
    NoteEntry,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteSendParams,
    NoteStatus,
    PingParams,
    PocketFileInfo,
    PocketManifestResult,
    PocketOffsetParams,
    PocketOffsetResult,
    PocketPullParams,
    PocketPushParams,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.protocol import (
    FrameTooLargeError,
    InvalidMagicError,
    MalformedJsonRpcError,
    ProtocolError,
    encode_frame,
    encode_jsonrpc,
    parse_jsonrpc,
    read_frame,
    write_frame,
)
from bridge_core.retry import (
    async_retry_with_backoff,
    is_sharing_violation,
    retry_with_backoff,
)
from bridge_core.security import (
    AuthenticationError,
    PathTraversalError,
    PSKAuthenticator,
    SecurityError,
    TokenReplayError,
    create_client_ssl_context,
    create_server_ssl_context,
    validate_safe_path,
)
from bridge_core.transport import (
    AsyncTransportClient,
    AsyncTransportServer,
    RpcCallError,
    TransportError,
)

__version__ = "0.1.0-dev"

__all__ = [
    "FRAME_HEADER_SIZE",
    "FRAME_MAGIC",
    "MAX_PAYLOAD_SIZE",
    "AsyncTransportClient",
    "AsyncTransportServer",
    "AtomicJsonlLogger",
    "AuditLogEntry",
    "AuditStatus",
    "AuthenticationError",
    "BridgeConfig",
    "ConnectionConfig",
    "ConnectionState",
    "DecodedOutput",
    "ExecConfig",
    "ExecRequestParams",
    "ExecResult",
    "ExecTimeoutErrorData",
    "FrameTooLargeError",
    "HeartbeatConfig",
    "HeartbeatManager",
    "HeartbeatTimeoutError",
    "InvalidMagicError",
    "JsonRpcError",
    "JsonRpcErrorResponse",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "LoggingConfig",
    "MalformedJsonRpcError",
    "NodeConfig",
    "NodeOS",
    "NodeStatus",
    "NoteDeliveryResult",
    "NoteEntry",
    "NoteHistoryParams",
    "NoteHistoryResult",
    "NoteSendParams",
    "NoteStatus",
    "PSKAuthenticator",
    "PathTraversalError",
    "PingParams",
    "PocketConfig",
    "PocketFileInfo",
    "PocketManifestResult",
    "PocketOffsetParams",
    "PocketOffsetResult",
    "PocketPullParams",
    "PocketPushParams",
    "PongResult",
    "ProtocolError",
    "RpcCallError",
    "RpcErrorCode",
    "RpcMethod",
    "SecurityError",
    "TokenReplayError",
    "TransportError",
    "WindowsOutputDecoder",
    "__version__",
    "async_retry_with_backoff",
    "create_client_ssl_context",
    "create_server_ssl_context",
    "encode_frame",
    "encode_jsonrpc",
    "is_sharing_violation",
    "parse_jsonrpc",
    "read_frame",
    "retry_with_backoff",
    "setup_logging",
    "validate_safe_path",
    "write_frame",
]
