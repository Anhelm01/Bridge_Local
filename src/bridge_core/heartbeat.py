"""
bridge_core.heartbeat — Движок отказоустойчивого мониторинга доступности (Fail-Fast Heartbeat).

Реализует:
  - Мгновенное зондирование (Quick Probe) перед выполнением команд с таймаутом <= 1.5 сек.
  - Фоновый цикл периодических ping/pong проверок (HeartbeatManager).
  - Смену состояний узла: CONNECTED -> UNREACHABLE при сбоях без зависания на ОС-таймаутах.
  - Расчёт задержки сети (RTT) в микросекундах и Dev-Mode трассировку.
  - Коллбэки на восстановление и потерю связи.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bridge_core.config import HeartbeatConfig
from bridge_core.models import (
    ConnectionState,
    JsonRpcRequest,
    NodeOS,
    PingParams,
    PongResult,
    RpcMethod,
)

if TYPE_CHECKING:
    from bridge_core.transport import AsyncTransportClient

logger = logging.getLogger(__name__)


class HeartbeatTimeoutError(Exception):
    """Превышено время ожидания ответа heartbeat (узел недоступен)."""


class HeartbeatManager:
    """
    Менеджер liveness-мониторинга между Linux клиентом и Windows агентом.

    Запускает фоновую задачу пинга и управляет переходом состояний.
    """

    def __init__(
        self,
        client: AsyncTransportClient,
        config: HeartbeatConfig | None = None,
        client_os: NodeOS = NodeOS.LINUX,
        on_state_change: Callable[[ConnectionState, ConnectionState], Any] | None = None,
    ) -> None:
        self.client = client
        self.config = config or HeartbeatConfig()
        self.client_os = client_os
        self.on_state_change = on_state_change

        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._task: asyncio.Task[None] | None = None
        self._consecutive_misses: int = 0
        self._last_rtt_ms: float = 0.0
        self._last_pong: PongResult | None = None
        self._stop_event = asyncio.Event()

    @property
    def state(self) -> ConnectionState:
        """Текущее состояние подключения."""
        return self._state

    @property
    def last_rtt_ms(self) -> float:
        """Задержка последнего ping/pong в миллисекундах."""
        return self._last_rtt_ms

    @property
    def last_pong(self) -> PongResult | None:
        """Данные последнего полученного pong (CPU, RAM, Uptime)."""
        return self._last_pong

    def set_state(self, new_state: ConnectionState) -> None:
        """Переключает состояние подключения и оповещает слушателей."""
        old_state = self._state
        if old_state != new_state:
            self._state = new_state
            logger.info(
                "[HEARTBEAT] Смена состояния: %s -> %s (пропусков: %d)",
                old_state.value,
                new_state.value,
                self._consecutive_misses,
            )
            if self.on_state_change:
                try:
                    self.on_state_change(old_state, new_state)
                except Exception as e:
                    logger.error("Ошибка в коллбэке on_state_change: %s", e)

    async def probe(self, timeout_sec: float | None = None) -> float:
        """
        Мгновенная проверка доступности узла (Fail-Fast Probe).

        Отправляет одиночный ping и ждёт pong не более timeout_sec
        (по умолчанию config.timeout_sec <= 1.5s).

        Returns:
            RTT в миллисекундах при успехе.

        Raises:
            HeartbeatTimeoutError: Если узел не ответил за отведённый лимит.
        """
        timeout = timeout_sec or self.config.timeout_sec
        t0 = time.perf_counter_ns()

        ping_params = PingParams(client_os=self.client_os)
        req = JsonRpcRequest(
            method=RpcMethod.HEARTBEAT_PING,
            params=ping_params.model_dump(),
        )

        try:
            resp = await asyncio.wait_for(
                self.client.call_rpc(req),
                timeout=timeout,
            )
            rtt_ms = (time.perf_counter_ns() - t0) / 1_000_000
            self._last_rtt_ms = rtt_ms
            self._consecutive_misses = 0

            # Парсим результат
            self._last_pong = PongResult.model_validate(resp.result)
            self.set_state(ConnectionState.CONNECTED)

            logger.debug(
                "[DEV-HEARTBEAT] Probe OK: RTT=%.2f ms, agent_status=%s, cpu=%.1f%%",
                rtt_ms,
                self._last_pong.status,
                self._last_pong.cpu_percent,
            )
            return rtt_ms

        except TimeoutError as e:
            self._consecutive_misses += 1
            if self._consecutive_misses >= self.config.max_missed:
                self.set_state(ConnectionState.UNREACHABLE)
            logger.warning(
                "[DEV-HEARTBEAT] Probe TIMEOUT (> %.2f с), пропуск %d/%d",
                timeout,
                self._consecutive_misses,
                self.config.max_missed,
            )
            raise HeartbeatTimeoutError(
                f"Узел не ответил на heartbeat probe за {timeout:.1f} сек"
            ) from e

        except Exception as e:
            self._consecutive_misses += 1
            self.set_state(ConnectionState.UNREACHABLE)
            logger.error("[DEV-HEARTBEAT] Ошибка probe соединения: %s", e)
            raise HeartbeatTimeoutError(f"Сбой соединения при probe: {e}") from e

    def start(self) -> None:
        """Запускает фоновую задачу периодического пинга."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="HeartbeatLoop")
        logger.debug(
            "HeartbeatManager запущен: интервал=%.1fs, таймаут=%.1fs",
            self.config.interval_sec,
            self.config.timeout_sec,
        )

    async def stop(self) -> None:
        """Останавливает фоновый мониторинг."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.set_state(ConnectionState.DISCONNECTED)
        logger.debug("HeartbeatManager остановлен")

    async def _loop(self) -> None:
        """Фоновый цикл пинга."""
        while not self._stop_event.is_set():
            with contextlib.suppress(HeartbeatTimeoutError):
                await self.probe()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.interval_sec,
                )
            except TimeoutError:
                continue
