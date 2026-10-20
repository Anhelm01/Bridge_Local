"""
bridge_client_linux.clipboard — Кросс-десктопный адаптер буфера обмена для Linux.

Поддерживает:
  - Wayland: wl-copy / wl-paste
  - X11: xclip / xsel
  - Автоматическое определение типов содержимого (файлы text/uri-list, изображения image/png, текст text/plain).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipboardData:
    """Типизированные данные, извлечённые из буфера обмена."""

    data_type: str  # 'files' | 'image' | 'text' | 'empty'
    files: list[Path] | None = None
    image_bytes: bytes | None = None
    suggested_filename: str | None = None
    text: str | None = None


def is_wayland() -> bool:
    """Определяет, работает ли сессия под Wayland."""
    return bool(
        os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


def copy_text_to_clipboard(text: str) -> bool:
    """
    Копирует строку в системный буфер обмена.

    Возвращает True в случае успеха, False если утилиты недоступны.
    """
    if not text:
        return False

    # 1. Попытка через Wayland (wl-copy)
    if shutil.which("wl-copy"):
        try:
            # wl-copy форкается в фон для поддержания selection.
            # Необходимо перенаправить stdout/stderr в DEVNULL, чтобы subprocess не зависал.
            proc = subprocess.run(
                ["wl-copy", text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
                env=os.environ,
            )
            return proc.returncode == 0
        except Exception as e:
            logger.debug("[CLIPBOARD] wl-copy failed: %s", e)

    # 2. Попытка через X11 (xclip)
    if shutil.which("xclip"):
        try:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
                env=os.environ,
            )
            return proc.returncode == 0
        except Exception as e:
            logger.debug("[CLIPBOARD] xclip failed: %s", e)

    # 3. Попытка через X11 (xsel)
    if shutil.which("xsel"):
        try:
            proc = subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
                env=os.environ,
            )
            return proc.returncode == 0
        except Exception as e:
            logger.debug("[CLIPBOARD] xsel failed: %s", e)

    return False


def get_clipboard_content() -> ClipboardData:
    """
    Анализирует содержимое буфера обмена и возвращает типизированную структуру.

    Приоритет типов:
      1. Файлы (text/uri-list) — например, файл скопирован в файловом менеджере.
      2. Изображение (image/png, image/jpeg) — скриншот или скопированная картинка.
      3. Обычный текст (text/plain).
    """
    # ── Wayland (wl-paste) ───────────────────────────────────────────────────
    if shutil.which("wl-paste"):
        try:
            # Получаем список доступных MIME-типов
            types_proc = subprocess.run(
                ["wl-paste", "--list-types"],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ,
            )
            available_types = [t.strip() for t in types_proc.stdout.splitlines() if t.strip()]

            # 1. Файлы через text/uri-list
            if "text/uri-list" in available_types:
                raw_uris = subprocess.run(
                    ["wl-paste", "--type", "text/uri-list"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=os.environ,
                ).stdout
                files: list[Path] = []
                for line in raw_uris.splitlines():
                    line = line.strip()
                    if line.startswith("file://"):
                        local_path = urllib.parse.unquote(line[7:])
                        p = Path(local_path)
                        if p.exists():
                            files.append(p)
                if files:
                    return ClipboardData(data_type="files", files=files)

            # 2. Изображение
            img_type = next((t for t in available_types if t.startswith("image/")), None)
            if img_type:
                ext = "png" if "png" in img_type else "jpg"
                img_data = subprocess.run(
                    ["wl-paste", "--type", img_type],
                    capture_output=True,
                    check=False,
                    env=os.environ,
                ).stdout
                if img_data:
                    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{now_str}.{ext}"
                    return ClipboardData(
                        data_type="image",
                        image_bytes=img_data,
                        suggested_filename=filename,
                    )

            # 3. Текст
            text_data = subprocess.run(
                ["wl-paste", "--type", "text/plain"],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ,
            ).stdout
            if text_data and text_data.strip():
                return ClipboardData(data_type="text", text=text_data)

        except Exception as e:
            logger.debug("[CLIPBOARD] Ошибка чтения через wl-paste: %s", e)

    # ── X11 (xclip) ──────────────────────────────────────────────────────────
    if shutil.which("xclip"):
        try:
            # 1. Проверяем targets в xclip
            targets_proc = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ,
            )
            targets = [t.strip() for t in targets_proc.stdout.splitlines() if t.strip()]

            # 1. Файлы
            if "text/uri-list" in targets:
                raw_uris = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=os.environ,
                ).stdout
                files = []
                for line in raw_uris.splitlines():
                    line = line.strip()
                    if line.startswith("file://"):
                        local_path = urllib.parse.unquote(line[7:])
                        p = Path(local_path)
                        if p.exists():
                            files.append(p)
                if files:
                    return ClipboardData(data_type="files", files=files)

            # 2. Изображение
            img_target = next((t for t in targets if t.startswith("image/")), None)
            if img_target:
                ext = "png" if "png" in img_target else "jpg"
                img_data = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", img_target, "-o"],
                    capture_output=True,
                    check=False,
                    env=os.environ,
                ).stdout
                if img_data:
                    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{now_str}.{ext}"
                    return ClipboardData(
                        data_type="image",
                        image_bytes=img_data,
                        suggested_filename=filename,
                    )

            # 3. Текст
            text_data = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ,
            ).stdout
            if text_data and text_data.strip():
                return ClipboardData(data_type="text", text=text_data)

        except Exception as e:
            logger.debug("[CLIPBOARD] Ошибка чтения через xclip: %s", e)

    return ClipboardData(data_type="empty")
