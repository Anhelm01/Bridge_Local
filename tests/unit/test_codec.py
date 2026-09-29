"""
Тесты для bridge_core.codec — декодер вывода Windows (UTF-8, CP1251, CP866, BOM, ANSI).
"""

from __future__ import annotations

from bridge_core.codec import WindowsOutputDecoder


class TestWindowsOutputDecoder:
    """Тесты декодера WindowsOutputDecoder."""

    def test_decode_empty(self) -> None:
        res = WindowsOutputDecoder.decode(b"")
        assert res.text == ""
        assert res.encoding_used == "empty"
        assert not res.had_errors

    def test_decode_utf8_cyrillic(self) -> None:
        source = "Проверка кодировки UTF-8: Службы Windows запущены"
        raw = source.encode("utf-8")
        res = WindowsOutputDecoder.decode(raw)
        assert res.text == source
        assert res.encoding_used == "utf-8"
        assert not res.had_errors

    def test_decode_utf8_with_bom(self) -> None:
        source = "Текст с UTF-8 BOM"
        raw = b"\xef\xbb\xbf" + source.encode("utf-8")
        res = WindowsOutputDecoder.decode(raw)
        assert res.text == source
        assert res.had_bom is True
        assert res.encoding_used == "utf-8-sig"

    def test_decode_utf16_le_with_bom(self) -> None:
        source = "PowerShell UTF-16 LE вывод"
        raw = b"\xff\xfe" + source.encode("utf-16-le")
        res = WindowsOutputDecoder.decode(raw)
        assert res.text == source
        assert res.had_bom is True
        assert res.encoding_used == "utf-16-le"

    def test_decode_cp1251(self) -> None:
        source = "Тестовая строка в кодировке Windows-1251"
        raw = source.encode("cp1251")
        res = WindowsOutputDecoder.decode(raw)
        assert res.text == source
        assert res.encoding_used == "cp1251"
        assert not res.had_errors

    def test_decode_cp866(self) -> None:
        source = "Вывод консоли cmd.exe в кодировке CP866"
        raw = source.encode("cp866")
        res = WindowsOutputDecoder.decode(raw, preferred_encoding="cp866")
        assert res.text == source
        assert res.encoding_used == "cp866"
        assert not res.had_errors

    def test_normalize_crlf_to_lf(self) -> None:
        raw = b"line1\r\nline2\r\nline3\r\n"
        res = WindowsOutputDecoder.decode(raw, normalize_newlines=True)
        assert res.text == "line1\nline2\nline3\n"
        assert "\r" not in res.text

    def test_keep_crlf_when_disabled(self) -> None:
        raw = b"line1\r\nline2\r\n"
        res = WindowsOutputDecoder.decode(raw, normalize_newlines=False)
        assert res.text == "line1\r\nline2\r\n"

    def test_strip_ansi_escape_codes(self) -> None:
        raw = b"\x1b[32m[OK]\x1b[0m \x1b[1mProcess started\x1b[0m"
        res = WindowsOutputDecoder.decode(raw, strip_ansi=True)
        assert res.text == "[OK] Process started"

    def test_fallback_replace_on_corrupted_bytes(self) -> None:
        # Невалидная последовательность байтов для utf-8
        bad_bytes = b"\xff\xff\xff\x00\x80\x81"
        res = WindowsOutputDecoder.decode(bad_bytes)
        assert res.text != ""  # Не упало с ошибкой
        # Либо распозналось как cp1251/cp866, либо fallback на utf-8-replace
        assert res.encoding_used in ("cp1251", "cp866", "utf-8-replace")
