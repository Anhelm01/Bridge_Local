"""
Тесты для bridge_core.security — PSK аутентификация, защита от replay и Path Traversal.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from bridge_core.security import (
    AuthenticationError,
    PathTraversalError,
    PSKAuthenticator,
    TokenReplayError,
    validate_safe_path,
)


class TestPSKAuthenticator:
    """Тесты аутентификации по общему ключу (PSK + HMAC)."""

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            PSKAuthenticator(psk_token="")

    def test_generate_and_verify_success(self) -> None:
        auth = PSKAuthenticator(psk_token="my-super-secret-key-12345")
        headers = auth.generate_auth_header()

        assert "auth_timestamp" in headers
        assert "auth_nonce" in headers
        assert "auth_signature" in headers

        # Проверка проходит успешно
        assert auth.verify_auth_params(headers) is True

    def test_wrong_signature_rejected(self) -> None:
        auth = PSKAuthenticator(psk_token="key-A")
        headers = auth.generate_auth_header()
        headers["auth_signature"] = "bad_signature_00000000000000000000000000000000"

        with pytest.raises(AuthenticationError):
            auth.verify_auth_params(headers)

    def test_different_key_rejected(self) -> None:
        client_auth = PSKAuthenticator(psk_token="secret-one")
        server_auth = PSKAuthenticator(psk_token="secret-two")

        headers = client_auth.generate_auth_header()
        with pytest.raises(AuthenticationError):
            server_auth.verify_auth_params(headers)

    def test_replay_attack_rejected(self) -> None:
        auth = PSKAuthenticator(psk_token="secret-key")
        headers = auth.generate_auth_header()

        # Первая попытка успешна
        assert auth.verify_auth_params(headers) is True

        # Вторая попытка с тем же nonce — Replay Attack!
        with pytest.raises(TokenReplayError):
            auth.verify_auth_params(headers)

    def test_clock_skew_old_timestamp_rejected(self) -> None:
        auth = PSKAuthenticator(psk_token="secret-key", max_clock_skew_sec=5.0)
        headers = auth.generate_auth_header()

        # Подменяем timestamp на 10 секунд назад
        old_ts = time.time() - 10.0
        headers["auth_timestamp"] = f"{old_ts:.3f}"

        with pytest.raises(TokenReplayError):
            auth.verify_auth_params(headers)

    def test_missing_params_rejected(self) -> None:
        auth = PSKAuthenticator(psk_token="secret-key")
        with pytest.raises(AuthenticationError):
            auth.verify_auth_params({"auth_timestamp": "123.4"})


class TestPathTraversal:
    """Тесты защиты от Path Traversal в кармане."""

    def test_safe_relative_path(self, tmp_path: Path) -> None:
        safe_file = validate_safe_path(tmp_path, "sub/dir/file.txt")
        assert safe_file == (tmp_path / "sub/dir/file.txt").resolve()

    def test_safe_filename_only(self, tmp_path: Path) -> None:
        safe_file = validate_safe_path(tmp_path, "document.pdf")
        assert safe_file == (tmp_path / "document.pdf").resolve()

    def test_traversal_dotdot_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PathTraversalError):
            validate_safe_path(tmp_path, "../../etc/passwd")

    def test_traversal_nested_dotdot_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PathTraversalError):
            validate_safe_path(tmp_path, "folder/../../../secret.txt")

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PathTraversalError):
            validate_safe_path(tmp_path, "/etc/shadow")
