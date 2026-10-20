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
import struct
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
    return ctx


# ---------------------------------------------------------------------------
# AEAD End-to-End Encryption & HKDF Key Derivation (Section 5)
# ---------------------------------------------------------------------------

HKDF_AEAD_SALT = b"BridgeLocal_v0.2.0_AEAD_Salt"
HKDF_INFO_CLIENT_TO_SERVER = b"bridge_client_to_server_key"
HKDF_INFO_SERVER_TO_CLIENT = b"bridge_server_to_client_key"


def derive_hkdf_keys(psk_token: str) -> tuple[bytes, bytes]:
    """
    Генерирует криптографические суб-ключи шифрования для обоих направлений
    на основе общего секрета PSK (Pre-Shared Key) по стандарту HKDF (RFC 5869).

    Returns:
        Кортеж (client_key, server_key) по 32 байта (256 бит) каждый.
    """
    ikm = psk_token.encode("utf-8") if isinstance(psk_token, str) else psk_token

    def _hkdf_expand(salt: bytes, info: bytes, length: int = 32) -> bytes:
        # 1. HKDF-Extract
        prk = hmac.new(salt, ikm, hashlib.sha256).digest()
        # 2. HKDF-Expand
        t = b""
        okm = b""
        i = 1
        while len(okm) < length:
            t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
            okm += t
            i += 1
        return okm[:length]

    client_key = _hkdf_expand(HKDF_AEAD_SALT, HKDF_INFO_CLIENT_TO_SERVER, 32)
    server_key = _hkdf_expand(HKDF_AEAD_SALT, HKDF_INFO_SERVER_TO_CLIENT, 32)
    return client_key, server_key


class AeadFrameCipher:
    """
    Двунаправленный криптографический контекст для защиты фреймов протокола.

    Реализует:
      - Сквозное AEAD шифрование (AES-256-GCM) полезной нагрузки.
      - Аутентификацию заголовка (AAD: MAGIC + LEN + SEQ).
      - Защиту от повтора (Replay Attack) и перестановок пакетов через
        монотонные 64-битные счётчики последовательности (Sequence Numbers).
      - Изоляцию ключей отправки и приёма (разные суб-ключи для исключения reflection атак).
    """

    def __init__(
        self,
        send_key: bytes,
        recv_key: bytes,
        is_client: bool = True,
    ) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self.is_client = is_client
        self._send_key = send_key
        self._recv_key = recv_key
        self._send_cipher = AESGCM(send_key)
        self._recv_cipher = AESGCM(recv_key)

        self.send_seq: int = 0
        self.last_recv_seq: int = -1

    @classmethod
    def for_client(cls, psk_token: str) -> AeadFrameCipher:
        """Создаёт контекст шифрования для клиентской стороны."""
        c_key, s_key = derive_hkdf_keys(psk_token)
        return cls(send_key=c_key, recv_key=s_key, is_client=True)

    @classmethod
    def for_server(cls, psk_token: str) -> AeadFrameCipher:
        """Создаёт контекст шифрования для серверной стороны."""
        c_key, s_key = derive_hkdf_keys(psk_token)
        return cls(send_key=s_key, recv_key=c_key, is_client=False)

    def encrypt_frame(self, payload: bytes | str) -> bytes:
        """
        Шифрует payload и упаковывает в защищённый бинарный фрейм 'BE'.

        Формат:
          [0..1] MAGIC: 'BE' (0x42 0x45)
          [2..5] LEN: uint32 Big-Endian (8 + 12 + len(payload) + 16)
          [6..13] SEQ: uint64 Big-Endian
          [14..25] NONCE: 12 байт (4b random + 8b seq)
          [26..] CIPHERTEXT + TAG (AES-256-GCM)
        """
        raw_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload

        seq = self.send_seq
        self.send_seq += 1

        # Nonce = 4 случайных байта + 8 байт счётчика
        nonce = secrets.token_bytes(4) + struct.pack("!Q", seq)

        # Длина тела фрейма (SEQ + NONCE + CIPHERTEXT + TAG)
        body_len = 8 + 12 + len(raw_bytes) + 16
        header = b"\x42\x45" + struct.pack("!I", body_len)

        # Дополнительные аутентифицированные данные (AAD): header + seq
        aad = header + struct.pack("!Q", seq)

        ciphertext = self._send_cipher.encrypt(nonce, raw_bytes, aad)

        return header + struct.pack("!Q", seq) + nonce + ciphertext

    def decrypt_frame(self, header: bytes, body: bytes) -> bytes:
        """
        Проверяет и расшифровывает полученный 'BE' фрейм.

        Args:
            header: 6 байт заголовка (MAGIC + LEN).
            body: Тело фрейма длиной LEN.

        Returns:
            Расшифрованный исходный payload в байтах.

        Raises:
            TokenReplayError: Если нарушен порядок или обнаружен повторный пакет.
            AuthenticationError: Если подпись AEAD или контрольная сумма не совпала.
        """
        from cryptography.exceptions import InvalidTag

        if len(body) < 36:  # 8 (SEQ) + 12 (NONCE) + 16 (TAG)
            raise AuthenticationError(
                "Повреждённый AEAD-фрейм: длина меньше минимального размера 36 байт"
            )

        seq = struct.unpack("!Q", body[:8])[0]
        if seq <= self.last_recv_seq:
            logger.error(
                "[AEAD-REPLAY] Обнаружена повторная передача пакета: seq=%d <= last=%d",
                seq,
                self.last_recv_seq,
            )
            raise TokenReplayError(
                f"Replay-атака или нарушение порядка пакетов: seq {seq} <= {self.last_recv_seq}"
            )

        nonce = body[8:20]
        ciphertext = body[20:]

        aad = header + body[:8]

        try:
            plaintext = self._recv_cipher.decrypt(nonce, ciphertext, aad)
        except InvalidTag as e:
            logger.error(
                "[AEAD-AUTH-FAILED] Ошибка аутентификации AEAD тега! Данные подменены или неверный PSK."
            )
            raise AuthenticationError(
                "Сбой верификации AEAD: неверный ключ PSK или подмена пакета (MiTM)"
            ) from e

        self.last_recv_seq = seq
        return plaintext
