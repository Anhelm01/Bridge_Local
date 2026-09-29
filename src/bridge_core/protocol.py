"""
bridge_core.protocol — Фрейминг бинарного протокола и сериализация JSON-RPC.

Реализует:
  - Length-Prefix Binary Framing поверх TCP:
    MAGIC (2 байта: 0x42 0x52 / 'BR') + LEN (4 байта uint32 Big-Endian) + PAYLOAD (UTF-8 JSON).
  - Асинхронное чтение и запись фреймов с валидацией границ и защитой от переполнения буфера.
  - Сериализацию / десериализацию JSON-RPC 2.0 сообщений (Request, Response, Error).
  - Dev-Mode трассировку сырых байтов и времени обработки.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from typing import Any

from bridge_core.models import (
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    MAX_PAYLOAD_SIZE,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Исключения протокола
# ---------------------------------------------------------------------------


class ProtocolError(Exception):
    """Базовое исключение для ошибок протокола фрейминга."""


class InvalidMagicError(ProtocolError):
    """Получены неверные магические байты фрейма."""


class FrameTooLargeError(ProtocolError):
    """Размер payload превышает допустимый максимум."""


class MalformedJsonRpcError(ProtocolError):
    """Payload не является корректным JSON-RPC 2.0 сообщением."""


# ---------------------------------------------------------------------------
# Кодирование и декодирование фреймов
# ---------------------------------------------------------------------------


def encode_frame(payload: bytes | str) -> bytes:
    """
    Кодирует полезную нагрузку в бинарный фрейм Bridge Local.

    Формат:
      [0..1] MAGIC: 0x42 0x52 ('BR')
      [2..5] LEN: uint32 Big-Endian (длина payload)
      [6..6+LEN-1] PAYLOAD: байты данных

    Args:
        payload: Строка UTF-8 или сырые байты.

    Returns:
        Сформированный бинарный фрейм.

    Raises:
        FrameTooLargeError: Если размер payload превышает MAX_PAYLOAD_SIZE.
    """
    raw_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    payload_len = len(raw_bytes)

    if payload_len > MAX_PAYLOAD_SIZE:
        raise FrameTooLargeError(
            f"Размер фрейма {payload_len} байт превышает максимум {MAX_PAYLOAD_SIZE} байт"
        )

    # MAGIC (2 байта) + длина uint32 Big-Endian (4 байта) + payload
    header = FRAME_MAGIC + struct.pack("!I", payload_len)
    return header + raw_bytes


async def read_frame(
    reader: asyncio.StreamReader,
    max_payload_size: int = MAX_PAYLOAD_SIZE,
    dev_logging: bool = True,
) -> bytes:
    """
    Асинхронно читает один полный бинарный фрейм из потока StreamReader.

    Гарантирует атомарное считывание заголовка и точного количества байт payload,
    обрабатывая фрагментацию TCP пакетов.

    Args:
        reader: Асинхронный поток чтения TCP сокета.
        max_payload_size: Максимально допустимый размер payload (байт).
        dev_logging: Включить ли детальную трассировку байтов.

    Returns:
        Сырые байты полезной нагрузки (payload).

    Raises:
        asyncio.IncompleteReadError: При разрыве соединения до завершения чтения.
        InvalidMagicError: Если первые 2 байта не совпадают с FRAME_MAGIC.
        FrameTooLargeError: Если объявленный размер превышает лимит.
    """
    t0 = time.perf_counter_ns()

    # 1. Читаем ровно 6 байт заголовка (2 magic + 4 length)
    header = await reader.readexactly(FRAME_HEADER_SIZE)

    # Проверка магических байтов
    magic = header[:2]
    if magic != FRAME_MAGIC:
        logger.error(
            "Неверные магические байты фрейма: %s (ожидалось %s)",
            magic.hex(),
            FRAME_MAGIC.hex(),
        )
        raise InvalidMagicError(f"Неверный MAGIC: {magic!r}, ожидался {FRAME_MAGIC!r}")

    # Распаковываем длину payload
    (payload_len,) = struct.unpack("!I", header[2:6])

    if payload_len > max_payload_size:
        logger.error(
            "Объявленная длина payload %d превышает лимит %d",
            payload_len,
            max_payload_size,
        )
        raise FrameTooLargeError(f"Payload {payload_len} байт превышает лимит {max_payload_size}")

    # 2. Читаем ровно payload_len байт данных
    payload = await reader.readexactly(payload_len)

    if dev_logging and logger.isEnabledFor(logging.DEBUG):
        elapsed_us = (time.perf_counter_ns() - t0) // 1000
        logger.debug(
            "[DEV-TRACE-FRAME] Считан фрейм: payload_len=%d b, elapsed=%d µs, preview=%.64r",
            payload_len,
            elapsed_us,
            payload[:64],
        )

    return payload


async def write_frame(
    writer: asyncio.StreamWriter,
    payload: bytes | str,
    dev_logging: bool = True,
) -> None:
    """
    Кодирует и асинхронно записывает фрейм в поток StreamWriter с последующим drain().

    Args:
        writer: Асинхронный поток записи TCP сокета.
        payload: Строка или байты данных.
        dev_logging: Трассировка времени и размера отправки.
    """
    t0 = time.perf_counter_ns()
    frame = encode_frame(payload)
    writer.write(frame)
    await writer.drain()

    if dev_logging and logger.isEnabledFor(logging.DEBUG):
        elapsed_us = (time.perf_counter_ns() - t0) // 1000
        logger.debug(
            "[DEV-TRACE-FRAME] Отправлен фрейм: total_size=%d b (payload=%d b), elapsed=%d µs",
            len(frame),
            len(frame) - FRAME_HEADER_SIZE,
            elapsed_us,
        )


# ---------------------------------------------------------------------------
# Сериализация и разбор JSON-RPC 2.0
# ---------------------------------------------------------------------------


def encode_jsonrpc(
    msg: JsonRpcRequest | JsonRpcResponse | JsonRpcErrorResponse,
) -> bytes:
    """Сериализует Pydantic JSON-RPC модель в байты UTF-8 JSON."""
    return msg.model_dump_json(exclude_none=False).encode("utf-8")


def parse_jsonrpc(
    data: bytes | str,
) -> JsonRpcRequest | JsonRpcResponse | JsonRpcErrorResponse:
    """
    Парсит сырые байты или строку в соответствующую модель JSON-RPC 2.0.

    Определяет тип сообщения по структуре полей:
      - Содержит 'method' -> JsonRpcRequest
      - Содержит 'error' -> JsonRpcErrorResponse
      - Содержит 'result' -> JsonRpcResponse

    Raises:
        MalformedJsonRpcError: При невалидном JSON или несоответствии стандарту.
    """
    try:
        raw: dict[str, Any] = json.loads(data)
    except Exception as e:
        raise MalformedJsonRpcError(f"Ошибка декодирования JSON: {e}") from e

    if not isinstance(raw, dict):
        raise MalformedJsonRpcError("JSON-RPC сообщение должно быть объектом")

    if raw.get("jsonrpc") != "2.0":
        raise MalformedJsonRpcError(f"Неподдерживаемая версия jsonrpc: {raw.get('jsonrpc')!r}")

    if "method" in raw:
        try:
            return JsonRpcRequest.model_validate(raw)
        except Exception as e:
            raise MalformedJsonRpcError(f"Невалидный JsonRpcRequest: {e}") from e

    if "error" in raw:
        try:
            return JsonRpcErrorResponse.model_validate(raw)
        except Exception as e:
            raise MalformedJsonRpcError(f"Невалидный JsonRpcErrorResponse: {e}") from e

    if "result" in raw:
        try:
            return JsonRpcResponse.model_validate(raw)
        except Exception as e:
            raise MalformedJsonRpcError(f"Невалидный JsonRpcResponse: {e}") from e

    raise MalformedJsonRpcError(f"Невозможно определить тип JSON-RPC сообщения: {list(raw.keys())}")
