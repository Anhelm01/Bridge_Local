"""
bridge_core.security — Аутентификация, защита от replay-атак, TLS и валидация путей.

Реализует:
  - PSK (Pre-Shared Key) аутентификацию с HMAC-SHA256 и nonce-проверкой против replay атак.
  - Настройку SSL/TLS контекстов для безопасной передачи по TCP в локальной сети.
  - Защиту от Path Traversal для операций в общей папке «карман».
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import ssl
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Базовое исключение для ошибок безопасности."""


class AuthenticationError(SecurityError):
    """Ошибка аутентификации PSK или невалидный токен."""


class PathTraversalError(SecurityError):
    """Попытка выхода за пределы доверенного каталога (Path Traversal)."""


class TokenReplayError(SecurityError):
    """Обнаружена повторная передача токена (Replay Attack)."""


# ---------------------------------------------------------------------------
# Аутентификация PSK + HMAC с защитой от Replay
# ---------------------------------------------------------------------------


class PSKAuthenticator:
    """
    Аутентификатор на базе общего ключа (Pre-Shared Key).

    Формирует и проверяет HMAC-SHA256 подпись с временной меткой и случайным nonce.
    Защищает от прослушивания и повторной отправки пакетов в локальной сети.
    """

    def __init__(
        self,
        psk_token: str,
        max_clock_skew_sec: float = 30.0,
    ) -> None:
        if not psk_token:
            raise ValueError("psk_token не может быть пустым")
        self._key = psk_token.encode("utf-8")
        self.max_clock_skew_sec = max_clock_skew_sec
        # Хранилище использованных nonce для защиты от replay (nonce -> expire_timestamp)
        self._seen_nonces: dict[str, float] = {}

    def generate_auth_header(self) -> dict[str, str]:
        """
        Генерирует словарь аутентификационных параметров для включения в RPC-запрос.

        Формат:
          timestamp: epoch в секундах (float)
          nonce: случайная hex-строка
          signature: HMAC-SHA256(key, f"{timestamp}:{nonce}")
        """
        now = time.time()
        nonce = secrets.token_hex(16)
        msg = f"{now:.3f}:{nonce}".encode()
        sig = hmac.new(self._key, msg, hashlib.sha256).hexdigest()

        return {
            "auth_timestamp": f"{now:.3f}",
            "auth_nonce": nonce,
            "auth_signature": sig,
        }

    def verify_auth_params(self, params: dict[str, str | float]) -> bool:
        """
        Проверяет подлинность параметров аутентификации.

        Raises:
            AuthenticationError: При несовпадении подписи или отсутствии ключей.
            TokenReplayError: Если nonce уже использовался или timestamp устарел.
        """
        try:
            ts_str = str(params["auth_timestamp"])
            nonce = str(params["auth_nonce"])
            sig = str(params["auth_signature"])
            ts = float(ts_str)
        except (KeyError, ValueError) as e:
            raise AuthenticationError(f"Отсутствуют обязательные auth-параметры: {e}") from e

        now = time.time()

        # 1. Проверяем допустимое расхождение часов
        if abs(now - ts) > self.max_clock_skew_sec:
            logger.warning(
                "Отклонение времени аутентификации слишком велико: |%f - %f| > %f",
                now,
                ts,
                self.max_clock_skew_sec,
            )
            raise TokenReplayError(
                f"Таймстемп устарел (разница {abs(now - ts):.1f} с > {self.max_clock_skew_sec} с)"
            )

        # 2. Очищаем устаревшие nonce из кеша
        self._cleanup_nonces(now)

        # 3. Проверяем, не использовался ли этот nonce
        if nonce in self._seen_nonces:
            logger.error("Обнаружен повторно использованный nonce: %s", nonce)
            raise TokenReplayError("Повторное использование auth_nonce (Replay Attack)")

        # 4. Проверяем HMAC подпись в постоянном времени (защита от timing attacks)
        expected_msg = f"{ts:.3f}:{nonce}".encode()
        expected_sig = hmac.new(self._key, expected_msg, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("Неверная HMAC-подпись запроса от клиента")
            raise AuthenticationError("Неверный токен аутентификации (HMAC mismatch)")

        # Запоминаем использованный nonce
        self._seen_nonces[nonce] = now + self.max_clock_skew_sec
        return True

    def _cleanup_nonces(self, now: float) -> None:
        """Удаляет просроченные nonce из памяти."""
        expired = [n for n, expire in self._seen_nonces.items() if expire < now]
        for n in expired:
            del self._seen_nonces[n]


# ---------------------------------------------------------------------------
# Защита от Path Traversal
# ---------------------------------------------------------------------------


def validate_safe_path(base_dir: Path | str, relative_path: str) -> Path:
    """
    Проверяет, что относительный путь строго находится внутри base_dir.

    Защищает общую папку «карман» от атак типа ../../etc/passwd или C:\\Windows\\System32.

    Args:
        base_dir: Корневая директория кармана.
        relative_path: Относительный путь к файлу.

    Returns:
        Абсолютный валидированный Path внутри base_dir.

    Raises:
        PathTraversalError: При попытке выйти за пределы base_dir.
    """
    base = Path(base_dir).resolve()
    # Запрещаем абсолютные пути в relative_path
    if os.path.isabs(relative_path):
        raise PathTraversalError(f"Абсолютные пути запрещены: {relative_path!r}")

    # Нормализуем и разрешаем целевой путь
    target = (base / relative_path).resolve()

    try:
        # Проверяем, что base является префиксом target
        target.relative_to(base)
    except ValueError as e:
        logger.error(
            "Попытка Path Traversal: base=%s, attempt=%s, resolved=%s",
            base,
            relative_path,
            target,
        )
        raise PathTraversalError(
            f"Путь '{relative_path}' выходит за пределы кармана: {target}"
        ) from e

    return target


# ---------------------------------------------------------------------------
# TLS / SSL Контексты
# ---------------------------------------------------------------------------


def create_server_ssl_context(
    cert_path: str | Path,
    key_path: str | Path,
) -> ssl.SSLContext:
    """Создаёт серверный SSLContext с поддержкой TLS 1.3/1.2."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    # Запрещаем небезопасные старые версии TLS
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def create_client_ssl_context(
    ca_cert_path: str | Path | None = None,
    insecure_no_verify: bool = False,
) -> ssl.SSLContext:
    """
    Создаёт клиентский SSLContext.

    Args:
        ca_cert_path: Путь к CA/сертификату сервера для проверки.
        insecure_no_verify: Если True — отключает проверку сертификата
            (для локальных self-signed тестов).
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    if insecure_no_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif ca_cert_path:
        ctx.load_verify_locations(cafile=str(ca_cert_path))
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.load_default_certs()

    return ctx
