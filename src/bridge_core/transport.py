"""
bridge_core.transport — Асинхронный TCP/TLS транспорт (Клиент и Сервер).

Реализует:
  - AsyncTransportServer: приём TCP-подключений, TLS, диспетчеризация JSON-RPC запросов.
  - AsyncTransportClient: клиентское подключение, TLS, вызов call_rpc с корреляцией ID.
  - Length-Prefix Binary Framing (BR + LEN + JSON).
  - Dev-Mode Hyper-Logging: микросекундные замеры, логирование сессий, IP и размеров фреймов.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from bridge_core.models import (
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    RpcErrorCode,
)
from bridge_core.protocol import (
    InvalidMagicError,
    ProtocolError,
    encode_jsonrpc,
    parse_jsonrpc,
    read_frame,
    write_frame,
)

logger = logging.getLogger(__name__)

# Тип асинхронного обработчика метода: (params, session_info) -> result_dict
RpcHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


class RpcCallError(Exception):
    """Исключение, выбрасываемое клиентом при получении JsonRpcErrorResponse."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"RPC Error [{code}]: {message}")
        self.code = code
        self.message = message
        self.data = data


class TransportError(Exception):
    """Сбой на транспортном уровне сокета."""


# ---------------------------------------------------------------------------
# Асинхронный TCP/TLS Сервер (для Windows Агента)
# ---------------------------------------------------------------------------


class AsyncTransportServer:
    """
    Асинхронный TCP сервер с поддержкой TLS и диспетчеризацией JSON-RPC 2.0.

    Принимает соединения, читает фреймы, маршрутизирует вызовы по зарегистрированным
    методам и возвращает ответы.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9732,
        ssl_context: ssl.SSLContext | None = None,
        dev_logging: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.dev_logging = dev_logging

        self._handlers: dict[str, RpcHandler] = {}
        self._server: asyncio.Server | None = None
        self._active_clients: set[asyncio.Task[None]] = set()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def register_handler(self, method: str, handler: RpcHandler) -> None:
        """Регистрирует обработчик для RPC метода."""
        self._handlers[method] = handler
        logger.debug("[SERVER] Зарегистрирован метод: %s", method)

    async def start(self) -> None:
        """Запускает прослушивание сокета."""
        if self._is_running:
            return

        self._server = await asyncio.start_server(
            self._handle_client_connection,
            host=self.host,
            port=self.port,
            ssl=self.ssl_context,
        )
        self._is_running = True

        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        tls_str = "с TLS" if self.ssl_context else "БЕЗ TLS (raw TCP)"
        logger.info(
            "[SERVER] Запущен на %s (%s, dev_logging=%s)",
            addrs,
            tls_str,
            self.dev_logging,
        )

    async def stop(self) -> None:
        """Останавливает сервер и завершает активные клиентские соединения."""
        if not self._is_running or not self._server:
            return

        logger.info("[SERVER] Остановка сервера...")
        self._is_running = False
        self._server.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._server.wait_closed(), timeout=1.0)

        # Отменяем активные клиентские сессии
        for task in list(self._active_clients):
            task.cancel()
        if self._active_clients:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    asyncio.gather(*self._active_clients, return_exceptions=True),
                    timeout=1.0,
                )

        logger.info("[SERVER] Сервер полностью остановлен")

    async def _handle_client_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Обрабатывает одну клиентскую сессию."""
        task = asyncio.current_task()
        if task:
            self._active_clients.add(task)

        peername = writer.get_extra_info("peername")
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        t_connect = time.perf_counter_ns()

        logger.info(
            "[DEV-SERVER-CONN] Новое подключение [%s] от %s",
            session_id,
            peername,
        )
        session_info: dict[str, Any] = {
            "session_id": session_id,
            "peername": peername,
            "connected_at_ns": t_connect,
        }

        try:
            while self._is_running:
                try:
                    payload = await read_frame(reader, dev_logging=self.dev_logging)
                except asyncio.IncompleteReadError:
                    logger.debug("[%s] Клиент закрыл соединение", session_id)
                    break
                except InvalidMagicError as e:
                    logger.warning("[%s] Разрыв из-за неверного MAGIC: %s", session_id, e)
                    break
                except ProtocolError as e:
                    logger.error("[%s] Ошибка протокола: %s", session_id, e)
                    break

                # Обрабатываем сообщение
                t_msg = time.perf_counter_ns()
                await self._process_message(payload, writer, session_info, t_msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[%s] Непредвиденная ошибка сессии: %s", session_id, e)
        finally:
            elapsed_ms = (time.perf_counter_ns() - t_connect) / 1_000_000
            logger.info(
                "[DEV-SERVER-CONN] Сессия [%s] завершена (длительность: %.1f мс)",
                session_id,
                elapsed_ms,
            )
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
            if task:
                self._active_clients.discard(task)

    async def _process_message(
        self,
        payload: bytes,
        writer: asyncio.StreamWriter,
        session_info: dict[str, Any],
        start_ns: int,
    ) -> None:
        """Парсит JSON-RPC запрос, вызывает обработчик и отправляет ответ."""
        try:
            msg = parse_jsonrpc(payload)
        except Exception as e:
            err_resp = JsonRpcErrorResponse(
                id="null",
                error=JsonRpcError(
                    code=RpcErrorCode.PARSE_ERROR,
                    message=f"Ошибка парсинга JSON-RPC: {e}",
                ),
            )
            await write_frame(writer, encode_jsonrpc(err_resp), dev_logging=self.dev_logging)
            return

        if not isinstance(msg, JsonRpcRequest):
            logger.warning(
                "[%s] Сервер получил не-Request: %s",
                session_info["session_id"],
                type(msg),
            )
            return

        # Ищем зарегистрированный обработчик
        handler = self._handlers.get(msg.method)
        if not handler:
            err_resp = JsonRpcErrorResponse(
                id=msg.id,
                error=JsonRpcError(
                    code=RpcErrorCode.METHOD_NOT_FOUND,
                    message=f"Метод '{msg.method}' не найден на узле",
                ),
            )
            await write_frame(writer, encode_jsonrpc(err_resp), dev_logging=self.dev_logging)
            return

        try:
            result = await handler(msg.params, session_info)
            resp = JsonRpcResponse(id=msg.id, result=result)
            resp_bytes = encode_jsonrpc(resp)
        except RpcCallError as e:
            err_resp = JsonRpcErrorResponse(
                id=msg.id,
                error=JsonRpcError(code=e.code, message=e.message, data=e.data),
            )
            resp_bytes = encode_jsonrpc(err_resp)
        except Exception as e:
            logger.exception(
                "[%s] Ошибка выполнения метода '%s': %s",
                session_info["session_id"],
                msg.method,
                e,
            )
            err_resp = JsonRpcErrorResponse(
                id=msg.id,
                error=JsonRpcError(
                    code=RpcErrorCode.INTERNAL_ERROR,
                    message=f"Внутренняя ошибка сервера: {e}",
                ),
            )
            resp_bytes = encode_jsonrpc(err_resp)

        duration_us = (time.perf_counter_ns() - start_ns) // 1000
        logger.debug(
            "[DEV-SERVER-RPC] [%s] %s (id=%s) -> ответ готов за %d µs (%d b)",
            session_info["session_id"],
            msg.method,
            msg.id,
            duration_us,
            len(resp_bytes),
        )
        await write_frame(writer, resp_bytes, dev_logging=self.dev_logging)


# ---------------------------------------------------------------------------
# Асинхронный TCP/TLS Клиент (для Linux Управляющего Хоста)
# ---------------------------------------------------------------------------


class AsyncTransportClient:
    """
    Асинхронный TCP клиент с поддержкой TLS для вызова JSON-RPC методов.

    Обеспечивает установку соединения, отправку запросов и получение ответов.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9732,
        ssl_context: ssl.SSLContext | None = None,
        connect_timeout: float = 5.0,
        dev_logging: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.connect_timeout = connect_timeout
        self.dev_logging = dev_logging

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._is_connected = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self._writer is not None

    async def connect(self) -> None:
        """
        Устанавливает TCP/TLS соединение с агентом.

        Raises:
            TransportError: Если не удалось подключиться в пределах таймаута.
        """
        if self.is_connected:
            return

        t0 = time.perf_counter_ns()
        logger.debug(
            "[DEV-CLIENT] Подключение к %s:%d (timeout=%.1fs, TLS=%s)...",
            self.host,
            self.port,
            self.connect_timeout,
            bool(self.ssl_context),
        )

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=self.ssl_context,
                ),
                timeout=self.connect_timeout,
            )
            self._is_connected = True
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
            logger.info(
                "[CLIENT] Успешно подключено к %s:%d за %.2f мс",
                self.host,
                self.port,
                elapsed_ms,
            )
        except TimeoutError as e:
            self._is_connected = False
            raise TransportError(
                f"Таймаут подключения к {self.host}:{self.port} ({self.connect_timeout} сек)"
            ) from e
        except Exception as e:
            self._is_connected = False
            raise TransportError(f"Не удалось подключиться к {self.host}:{self.port}: {e}") from e

    async def close(self) -> None:
        """Закрывает соединение с агентом."""
        self._is_connected = False
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._writer.wait_closed(), timeout=0.5)
            self._writer = None
            self._reader = None
        logger.debug("[CLIENT] Соединение закрыто")

    async def call_rpc(
        self,
        request: JsonRpcRequest,
        timeout_sec: float | None = None,
    ) -> JsonRpcResponse:
        """
        Отправляет JSON-RPC запрос и дожидается ответа.

        Args:
            request: Запрос JsonRpcRequest.
            timeout_sec: Таймаут ожидания ответа (секунды).

        Returns:
            Успешный JsonRpcResponse.

        Raises:
            TransportError: При разрыве соединения.
            RpcCallError: Если сервер вернул JsonRpcErrorResponse.
            TimeoutError: Если сервер не ответил за timeout_sec.
        """
        if not self.is_connected or not self._writer or not self._reader:
            await self.connect()

        assert self._writer is not None
        assert self._reader is not None

        async with self._lock:
            t0 = time.perf_counter_ns()
            req_bytes = encode_jsonrpc(request)

            # Отправка фрейма
            try:
                await write_frame(self._writer, req_bytes, dev_logging=self.dev_logging)
            except Exception as e:
                await self.close()
                raise TransportError(f"Ошибка отправки фрейма: {e}") from e

            # Ожидание ответа
            try:
                if timeout_sec:
                    resp_payload = await asyncio.wait_for(
                        read_frame(self._reader, dev_logging=self.dev_logging),
                        timeout=timeout_sec,
                    )
                else:
                    resp_payload = await read_frame(self._reader, dev_logging=self.dev_logging)
            except TimeoutError:
                logger.warning(
                    "[CLIENT] Таймаут ответа RPC (method=%s, id=%s, limit=%.1fs)",
                    request.method,
                    request.id,
                    timeout_sec or 0,
                )
                raise
            except Exception as e:
                await self.close()
                raise TransportError(f"Ошибка чтения ответа: {e}") from e

            # Разбор ответа
            msg = parse_jsonrpc(resp_payload)
            elapsed_us = (time.perf_counter_ns() - t0) // 1000

            if isinstance(msg, JsonRpcErrorResponse):
                logger.debug(
                    "[DEV-CLIENT-RPC] Ошибка RPC [%d]: %s (elapsed=%d µs)",
                    msg.error.code,
                    msg.error.message,
                    elapsed_us,
                )
                raise RpcCallError(
                    code=msg.error.code,
                    message=msg.error.message,
                    data=msg.error.data,
                )

            if isinstance(msg, JsonRpcResponse):
                logger.debug(
                    "[DEV-CLIENT-RPC] Успешный ответ id=%s (elapsed=%d µs)",
                    msg.id,
                    elapsed_us,
                )
                return msg

            raise ProtocolError(f"Неожиданный тип сообщения в ответ на запрос: {type(msg)}")

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_sec: float | None = None,
        source_node: str | None = None,
        target_node: str | None = None,
    ) -> Any:
        """
        Удобный метод вызова RPC с автоматической упаковкой в JsonRpcRequest
        и распаковкой результата (resp.result).

        Args:
            method: Имя RPC метода.
            params: Параметры вызова (словарь).
            timeout_sec: Таймаут ответа в секундах.
            source_node: Имя узла-отправителя (мульти-ноды).
            target_node: Имя целевого узла (мульти-ноды).

        Returns:
            Поле result из JsonRpcResponse.

        Raises:
            RpcCallError: При ошибке на стороне сервера.
            TransportError: При сетевом сбое.
            TimeoutError: При превышении таймаута.
        """
        request = JsonRpcRequest(
            method=method,
            params=params or {},
            source_node=source_node,
            target_node=target_node,
        )
        response = await self.call_rpc(request, timeout_sec=timeout_sec)
        return response.result

    async def disconnect(self) -> None:
        """Алиас для close() для единообразия клиентского API."""
        await self.close()
