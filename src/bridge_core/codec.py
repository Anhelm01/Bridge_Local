"""
bridge_core.codec — Декодер вывода консоли Windows с поддержкой кодовых страниц.

Решает проблему mojibake (битых символов кириллицы) из PowerShell/cmd:
  - Автоматическое распознавание и удаление BOM (UTF-8-SIG, UTF-16-LE, UTF-16-BE).
  - Приоритетная цепочка декодирования: UTF-8 -> CP1251 -> CP866 -> utf-8 (replace).
  - Нормализация переводов строк Windows (CRLF -> LF).
  - Очистка от управляющих ANSI-последовательностей.
  - Подробная Dev-Mode трассировка обнаруженных кодировок и байт.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Регулярка для удаления ANSI-последовательностей (escape codes)
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True)
class DecodedOutput:
    """Результат декодирования вывода."""

    text: str
    encoding_used: str
    had_errors: bool
    had_bom: bool = False


class WindowsOutputDecoder:
    """
    Интеллектуальный декодер сырых байтов вывода процессов Windows.

    Обеспечивает корректное чтение как UTF-8 потоков с chcp 65001,
    так и устаревших консольных потоков CP866/CP1251.
    """

    SUPPORTED_ENCODINGS: tuple[str, ...] = ("utf-8", "cp1251", "cp866")

    @classmethod
    def decode(
        cls,
        raw_bytes: bytes,
        normalize_newlines: bool = True,
        strip_ansi: bool = True,
        preferred_encoding: str | None = None,
    ) -> DecodedOutput:
        """
        Декодирует сырые байты в Unicode строку.

        Args:
            raw_bytes: Сырые байты из stdout/stderr процесса.
            normalize_newlines: Заменять CRLF (\r\n) на LF (\n).
            strip_ansi: Удалять ANSI escape-коды форматирования консоли.
            preferred_encoding: Явно предпочитаемая кодировка для первой попытки.

        Returns:
            DecodedOutput с расшифрованным текстом и метаданными.
        """
        if not raw_bytes:
            return DecodedOutput(
                text="",
                encoding_used="empty",
                had_errors=False,
                had_bom=False,
            )

        had_bom = False
        data_to_decode = raw_bytes

        # 1. Проверяем наличие BOM
        if raw_bytes.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
            had_bom = True
            data_to_decode = raw_bytes[3:]
            try:
                text = data_to_decode.decode("utf-8")
                return cls._finalize(
                    text,
                    "utf-8-sig",
                    had_errors=False,
                    had_bom=True,
                    normalize_newlines=normalize_newlines,
                    strip_ansi=strip_ansi,
                )
            except UnicodeDecodeError:
                pass

        if raw_bytes.startswith(b"\xff\xfe"):  # UTF-16 LE BOM
            try:
                text = raw_bytes[2:].decode("utf-16-le")
                return cls._finalize(
                    text,
                    "utf-16-le",
                    had_errors=False,
                    had_bom=True,
                    normalize_newlines=normalize_newlines,
                    strip_ansi=strip_ansi,
                )
            except UnicodeDecodeError:
                pass

        # 2. Формируем список кандидатов для декодирования
        encodings: list[str] = []
        if preferred_encoding:
            encodings.append(preferred_encoding.lower())
        for enc in cls.SUPPORTED_ENCODINGS:
            if enc not in encodings:
                encodings.append(enc)

        # 3. Пробуем строгие декодеры по очереди
        for enc in encodings:
            try:
                text = data_to_decode.decode(enc)
                logger.debug(
                    "[DEV-CODEC] Успешно декодировано через '%s' (%d байт -> %d символов)",
                    enc,
                    len(raw_bytes),
                    len(text),
                )
                return cls._finalize(
                    text,
                    enc,
                    had_errors=False,
                    had_bom=had_bom,
                    normalize_newlines=normalize_newlines,
                    strip_ansi=strip_ansi,
                )
            except (UnicodeDecodeError, LookupError):
                continue

        # 4. Fallback: UTF-8 с заменой невалидных байтов символом
        logger.warning(
            "[DEV-CODEC] Не удалось строго декодировать вывод кодировками %s; fallback utf-8",
            encodings,
        )
        text = data_to_decode.decode("utf-8", errors="replace")
        return cls._finalize(
            text,
            "utf-8-replace",
            had_errors=True,
            had_bom=had_bom,
            normalize_newlines=normalize_newlines,
            strip_ansi=strip_ansi,
        )

    @classmethod
    def _finalize(
        cls,
        text: str,
        encoding: str,
        had_errors: bool,
        had_bom: bool,
        normalize_newlines: bool,
        strip_ansi: bool,
    ) -> DecodedOutput:
        """Нормализация текста (переводы строк и ANSI-коды)."""
        res = text
        if normalize_newlines:
            res = res.replace("\r\n", "\n").replace("\r", "\n")
        if strip_ansi:
            res = ANSI_ESCAPE_RE.sub("", res)
        return DecodedOutput(
            text=res,
            encoding_used=encoding,
            had_errors=had_errors,
            had_bom=had_bom,
        )

    @classmethod
    def strip_ansi(cls, text: str) -> str:
        """Вспомогательный метод для очистки строки от ANSI escape-последовательностей."""
        return ANSI_ESCAPE_RE.sub("", text)
