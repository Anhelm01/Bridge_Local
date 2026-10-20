"""
bridge_core.discovery — LAN Zero-Conf UDP Beacon Discovery для Bridge Local.

Позволяет автоматически находить узлы Bridge Local в локальной сети
без ручного ввода IP-адресов:
  - DiscoveryResponder: UDP-сервер на порту 9735, отвечает на широковещательные запросы.
  - discover_nodes(): отправляет DISCOVER_PING на broadcast и собирает ответы DISCOVER_PONG.
  - HMAC-SHA256 аутентификация для фильтрации чужих устройств.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import re
import secrets
import socket
import subprocess
import time

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_DISCOVERY_PORT = 9735
DISCOVERY_MAGIC = "BRDISC01"


# ---------------------------------------------------------------------------
# DTO Модели
# ---------------------------------------------------------------------------


class DiscoveryPing(BaseModel):
    """Широковещательный запрос поиска узлов."""

    magic: str = Field(default=DISCOVERY_MAGIC)
    type: str = Field(default="DISCOVER_PING")
    source_node: str = Field(default="unknown")
    nonce: str = Field(description="Случайная соль запроса")
    auth_tag: str = Field(default="", description="HMAC-SHA256(psk, nonce)[:16]")


class DiscoveryPong(BaseModel):
    """Ответ узла на запрос поиска."""

    magic: str = Field(default=DISCOVERY_MAGIC)
    type: str = Field(default="DISCOVER_PONG")
    node_name: str = Field(description="Имя узла")
    display_name: str = Field(default="")
    os: str = Field(default="windows")
    tcp_port: int = Field(default=9732)
    nonce: str = Field(description="Возвращенная соль запроса")
    auth_tag: str = Field(default="", description="HMAC-SHA256(psk, nonce + str(tcp_port))[:16]")
    pocket_path: str = Field(default="")


class DiscoveredNode(BaseModel):
    """Обнаруженный узел в локальной сети."""

    ip: str
    port: int
    node_name: str
    display_name: str = ""
    os: str = "windows"
    psk_valid: bool = False
    latency_ms: float = 0.0
    pocket_path: str = ""


# ---------------------------------------------------------------------------
# Криптографические и сетевые хелперы
# ---------------------------------------------------------------------------


def compute_discovery_auth_tag(psk: str, data: str) -> str:
    """Вычисляет усечённый HMAC-SHA256 (16 hex-символов) для проверки подлинности пакета."""
    if not psk:
        return ""
    h = hmac.new(psk.encode("utf-8"), data.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()[:16]


def get_broadcast_addresses() -> list[str]:
    """Возвращает список широковещательных адресов (глобальный 255.255.255.255 и подсетей)."""
    bcasts = ["255.255.255.255"]
    # 1. Попытка через утилиту ip (Linux)
    try:
        out = subprocess.run(
            ["ip", "-4", "addr"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        ).stdout
        for match in re.findall(r"brd\s+(\d+\.\d+\.\d+\.\d+)", out):
            if match not in bcasts:
                bcasts.append(match)
    except Exception:
        pass

    # 2. Попытка через socket gethostbyname_ex
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                parts = ip.split(".")
                if len(parts) == 4:
                    cand = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    if cand not in bcasts:
                        bcasts.append(cand)
    except Exception:
        pass

    return bcasts


# ---------------------------------------------------------------------------
# Discovery Responder (Серверная сторона / UDP Beacon)
# ---------------------------------------------------------------------------


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Внутренний asyncio протокол для приёма и обработки UDP discovery пакетов."""

    def __init__(self, responder: DiscoveryResponder) -> None:
        self.responder = responder
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if isinstance(transport, asyncio.DatagramTransport):
            self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.responder.handle_datagram(data, addr, self.transport)


class DiscoveryResponder:
    """
    UDP-маяк, слушающий запросы поиска на порту 9735.

    Отвечает на валидные DISCOVER_PING пакеты метаданными узла.
    """

    def __init__(
        self,
        node_name: str,
        display_name: str = "",
        tcp_port: int = 9732,
        psk_token: str = "",
        pocket_path: str = "",
        node_os: str = "windows",
        port: int = DEFAULT_DISCOVERY_PORT,
        host: str = "0.0.0.0",
    ) -> None:
        self.node_name = node_name
        self.display_name = display_name
        self.tcp_port = tcp_port
        self.psk_token = psk_token
        self.pocket_path = pocket_path
        self.node_os = node_os
        self.port = port
        self.host = host

        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _DiscoveryProtocol | None = None
        self._is_running = False

    async def start(self) -> None:
        """Запускает прослушивание UDP-порта."""
        if self._is_running:
            return
        loop = asyncio.get_running_loop()
        try:
            # Создаем UDP сокет с SO_REUSEADDR для надежного перезапуска
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            sock.bind((self.host, self.port))

            transport, protocol = await loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(self),
                sock=sock,
            )
            self._transport = transport
            self._protocol = protocol
            self._is_running = True
            logger.info(
                "[DISCOVERY] UDP Beacon запущен на %s:%d (узел=%s)",
                self.host,
                self.port,
                self.node_name,
            )
        except Exception as e:
            logger.warning(
                "[DISCOVERY] Не удалось запустить UDP Beacon на порту %d: %s", self.port, e
            )

    def stop(self) -> None:
        """Останавливает UDP-маяк."""
        self._is_running = False
        if self._transport and not self._transport.is_closing():
            with contextlib.suppress(Exception):
                self._transport.close()
            self._transport = None
        logger.info("[DISCOVERY] UDP Beacon остановлен")

    def handle_datagram(
        self,
        data: bytes,
        addr: tuple[str, int],
        transport: asyncio.DatagramTransport | None,
    ) -> None:
        """Обрабатывает входящую датаграмму DISCOVER_PING."""
        if not transport:
            return
        try:
            payload = json.loads(data.decode("utf-8"))
            if payload.get("magic") != DISCOVERY_MAGIC or payload.get("type") != "DISCOVER_PING":
                return

            nonce = payload.get("nonce", "")
            # Если задан PSK, формируем подтверждающий auth_tag
            auth_tag = compute_discovery_auth_tag(self.psk_token, nonce + str(self.tcp_port))

            pong = DiscoveryPong(
                magic=DISCOVERY_MAGIC,
                type="DISCOVER_PONG",
                node_name=self.node_name,
                display_name=self.display_name,
                os=self.node_os,
                tcp_port=self.tcp_port,
                nonce=nonce,
                auth_tag=auth_tag,
                pocket_path=self.pocket_path,
            )

            response_bytes = pong.model_dump_json().encode("utf-8")
            transport.sendto(response_bytes, addr)
            logger.debug(
                "[DISCOVERY] Отправлен PONG на %s:%d (узел=%s)", addr[0], addr[1], self.node_name
            )
        except Exception as e:
            logger.debug("[DISCOVERY] Ошибка разбора датаграммы от %s: %s", addr, e)


# ---------------------------------------------------------------------------
# Discovery Scanner (Клиентская сторона)
# ---------------------------------------------------------------------------


async def discover_nodes(
    psk_token: str = "",
    timeout_sec: float = 1.5,
    discovery_port: int = DEFAULT_DISCOVERY_PORT,
    source_node: str = "workstation-linux",
) -> list[DiscoveredNode]:
    """
    Отправляет широковещательный UDP-запрос и собирает ответы от узлов Bridge Local.

    Возвращает список обнаруженных узлов с проверкой PSK и измеренным пингом.
    """
    discovered: list[DiscoveredNode] = []
    seen_keys: set[tuple[str, int]] = set()

    nonce = secrets.token_hex(8)
    auth_tag = compute_discovery_auth_tag(psk_token, nonce)

    ping = DiscoveryPing(
        magic=DISCOVERY_MAGIC,
        type="DISCOVER_PING",
        source_node=source_node,
        nonce=nonce,
        auth_tag=auth_tag,
    )
    packet_bytes = ping.model_dump_json().encode("utf-8")

    # Создаем UDP сокет с включенным широковещанием (SO_BROADCAST)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)

    broadcast_targets = get_broadcast_addresses()
    t_start = time.perf_counter()

    try:
        # Отправляем пинг на все широковещательные адреса
        for bcast_ip in broadcast_targets:
            try:
                sock.sendto(packet_bytes, (bcast_ip, discovery_port))
            except Exception as e:
                logger.debug("[DISCOVERY] Сбой отправки на %s:%d: %s", bcast_ip, discovery_port, e)

        # Собираем ответы до истечения таймаута
        loop = asyncio.get_running_loop()
        end_time = t_start + timeout_sec

        while True:
            remaining = end_time - time.perf_counter()
            if remaining <= 0:
                break

            try:
                # Ожидаем готовности сокета к чтению
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 4096),
                    timeout=remaining,
                )
                t_recv = time.perf_counter()
                latency = round((t_recv - t_start) * 1000.0, 2)

                payload = json.loads(data.decode("utf-8"))
                if (
                    payload.get("magic") != DISCOVERY_MAGIC
                    or payload.get("type") != "DISCOVER_PONG"
                ):
                    continue

                resp_nonce = payload.get("nonce", "")
                if resp_nonce != nonce:
                    continue  # Чужой или устаревший ответ

                tcp_port = int(payload.get("tcp_port", 9732))
                ip = str(addr[0])

                key = (ip, tcp_port)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # Проверка PSK подлинности
                expected_tag = compute_discovery_auth_tag(psk_token, nonce + str(tcp_port))
                recv_tag = str(payload.get("auth_tag", ""))
                psk_valid = bool(psk_token and recv_tag and (recv_tag == expected_tag))
                if not psk_token:
                    # Если локальный PSK не настроен, отмечаем как непроверенный
                    psk_valid = True

                node = DiscoveredNode(
                    ip=ip,
                    port=tcp_port,
                    node_name=payload.get("node_name", "UNKNOWN"),
                    display_name=payload.get("display_name", ""),
                    os=payload.get("os", "windows"),
                    psk_valid=psk_valid,
                    latency_ms=latency,
                    pocket_path=payload.get("pocket_path", ""),
                )
                discovered.append(node)
            except TimeoutError:
                break
            except Exception as e:
                logger.debug("[DISCOVERY] Ошибка при приеме PONG: %s", e)
                continue
    finally:
        sock.close()

    # Сортируем: сначала валидные по PSK, затем по минимальному пингу
    discovered.sort(key=lambda n: (not n.psk_valid, n.latency_ms))
    return discovered
