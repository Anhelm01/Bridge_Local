"""
bridge_agent_win.context_menu — Интеграция с контекстным меню Проводника Windows (Explorer).

Реализует:
  - Пункт меню «Отправить в Карман (Bridge Local)» по правому клику на файл или папку.
  - Установку и удаление регистрационных записей в реестре Windows (HKCU).
  - Генерацию standalone .reg файла для ручного импорта без прав администратора.
  - Обработчик drop_file_to_pocket: копирование файлов в локальный карман
    (откуда фоновый Watchdog службы BridgeLocalAgent автоматически пушит их на Linux).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from bridge_core.config import BridgeConfig

logger = logging.getLogger(__name__)

winreg: Any = None
try:
    import winreg as _winreg

    winreg = _winreg
except ImportError:
    pass

SHELL_KEY_FILES = r"Software\Classes\*\shell\BridgeLocalSend"
SHELL_KEY_DIRS = r"Software\Classes\Directory\shell\BridgeLocalSend"
MENU_LABEL = "Отправить в Карман (Bridge Local)"
DEFAULT_ICON = "shell32.dll,46"


def generate_reg_content(python_exe: str | None = None) -> str:
    """
    Генерирует содержимое файла Windows Registry (.reg) для регистрации контекстного меню.
    """
    exe = python_exe or (sys.executable if sys.platform == "win32" else "pythonw.exe")
    # Экранирование обратных слешей для формата .reg
    exe_escaped = exe.replace("\\", "\\\\")
    is_standalone_exe = getattr(sys, "frozen", False) or (
        exe.lower().endswith(".exe") and "python" not in Path(exe).name.lower()
    )
    if is_standalone_exe:
        cmd_str = f'\\"{exe_escaped}\\" drop \\"%1\\"'
    else:
        cmd_str = f'\\"{exe_escaped}\\" -m bridge_agent_win.context_menu drop \\"%1\\"'

    return f"""Windows Registry Editor Version 5.00

; ==============================================================================
; Bridge Local — Интеграция с контекстным меню Проводника Windows
; Отправка любого файла или папки в Карман по правому клику мыши (HKCU)
; ==============================================================================

; --- Для файлов ---
[HKEY_CURRENT_USER\\{SHELL_KEY_FILES}]
@="{MENU_LABEL}"
"Icon"="{DEFAULT_ICON}"

[HKEY_CURRENT_USER\\{SHELL_KEY_FILES}\\command]
@="{cmd_str}"

; --- Для каталогов ---
[HKEY_CURRENT_USER\\{SHELL_KEY_DIRS}]
@="{MENU_LABEL}"
"Icon"="{DEFAULT_ICON}"

[HKEY_CURRENT_USER\\{SHELL_KEY_DIRS}\\command]
@="{cmd_str}"
"""


def save_reg_file(output_path: Path | str, python_exe: str | None = None) -> Path:
    """
    Сохраняет .reg файл на диск.
    """
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    content = generate_reg_content(python_exe)
    out.write_text(content, encoding="utf-8")
    logger.info("[REG-EXPORT] Файл реестра сохранён: %s", out)
    return out


def install_context_menu(python_exe: str | None = None) -> bool:
    """
    Устанавливает пункт контекстного меню в реестр Windows текущего пользователя (HKCU).

    Returns:
        True если успешно, False если не Windows или произошла ошибка.
    """
    if winreg is None:
        logger.warning("Установка контекстного меню через winreg доступна только на Windows.")
        return False

    exe = python_exe or sys.executable
    is_standalone_exe = getattr(sys, "frozen", False) or (
        exe.lower().endswith(".exe") and "python" not in Path(exe).name.lower()
    )
    if is_standalone_exe:
        cmd_str = f'"{exe}" drop "%1"'
    else:
        cmd_str = f'"{exe}" -m bridge_agent_win.context_menu drop "%1"'

    try:
        # 1. Регистрация для файлов
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SHELL_KEY_FILES) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_LABEL)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, DEFAULT_ICON)

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{SHELL_KEY_FILES}\\command") as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)

        # 2. Регистрация для папок
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SHELL_KEY_DIRS) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_LABEL)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, DEFAULT_ICON)

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{SHELL_KEY_DIRS}\\command") as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)

        logger.info("[REG-INSTALL] Контекстное меню успешно установлено в HKCU.")
        return True
    except OSError as e:
        logger.error("[REG-ERROR] Ошибка записи в реестр Windows: %s", e)
        return False


def uninstall_context_menu() -> bool:
    """
    Удаляет пункт контекстного меню из реестра Windows (HKCU).
    """
    if winreg is None:
        logger.warning("Удаление контекстного меню через winreg доступно только на Windows.")
        return False

    def _delete_key_recursive(root: Any, subkey: str) -> None:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                        _delete_key_recursive(root, f"{subkey}\\{child}")
                    except OSError:
                        break
            winreg.DeleteKey(root, subkey)
        except FileNotFoundError:
            pass

    try:
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, SHELL_KEY_FILES)
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, SHELL_KEY_DIRS)
        logger.info("[REG-UNINSTALL] Контекстное меню успешно удалено из реестра.")
        return True
    except OSError as e:
        logger.error("[REG-ERROR] Ошибка при удалении ключей реестра: %s", e)
        return False


def drop_file_to_pocket(
    file_path: str | Path,
    config_path: Path | None = None,
) -> Path:
    """
    Копирует файл или каталог в локальный Карман для последующей синхронизации.

    Когда файл попадает в Карман, служба Windows (Watchdog) автоматически
    обнаруживает его и синхронизирует с удалённым узлом (Linux).
    """
    src = Path(file_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Файл или каталог не найден: {src}")

    cfg = BridgeConfig.load(config_path)
    pocket_dir = Path(cfg.pocket.path).expanduser().resolve()
    pocket_dir.mkdir(parents=True, exist_ok=True)

    dest = pocket_dir / src.name
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        # Для файлов: атомарное копирование через временный файл
        part = pocket_dir / f".{src.name}.part"
        shutil.copy2(src, part)
        os.replace(part, dest)

    logger.info("[POCKET-DROP] Объект '%s' успешно скопирован в карман: %s", src.name, dest)
    return dest


def main() -> None:
    """CLI точка входа для управления контекстным меню и обработки drop-событий."""
    args = sys.argv[1:]
    if not args:
        print(
            "Usage: python -m bridge_agent_win.context_menu "
            "[install | uninstall | generate-reg | drop <file>]"
        )
        sys.exit(1)

    cmd = args[0].lower()
    if cmd == "install":
        ok = install_context_menu()
        if ok:
            print("[OK] Контекстное меню 'Отправить в Карман (Bridge Local)' установлено.")
        else:
            print("[WARN] Не удалось установить в реестр (не Windows или ошибка доступа).")
            # Экспортируем .reg файл как альтернативу
            reg_p = save_reg_file(Path("windows_context_menu.reg"))
            print(f"[INFO] Создан файл реестра для ручного импорта: {reg_p}")

    elif cmd == "uninstall":
        ok = uninstall_context_menu()
        if ok:
            print("[OK] Контекстное меню удалено из реестра.")
        else:
            print("[WARN] Не удалось удалить ключи реестра.")

    elif cmd == "generate-reg":
        out = Path(args[1]) if len(args) > 1 else Path("windows_context_menu.reg")
        reg_p = save_reg_file(out)
        print(f"[OK] Файл реестра создан: {reg_p}")

    elif cmd == "drop":
        if len(args) < 2:
            print("[ERROR] Не указан путь к файлу для отправки.")
            sys.exit(1)
        target = args[1]
        try:
            dest = drop_file_to_pocket(target)
            print(f"[OK] Файл отправлен в Карман: {dest}")
        except Exception as e:
            print(f"[ERROR] Сбой отправки в Карман: {e}")
            sys.exit(1)
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
