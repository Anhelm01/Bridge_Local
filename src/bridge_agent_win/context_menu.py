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

# Автоматическое добавление каталога src/ в sys.path
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from bridge_core.config import BridgeConfig  # noqa: E402

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


def find_bridge_config(explicit_path: Path | str | None = None) -> Path | None:
    """Ищет конфигурационный файл bridge.toml в стандартных локациях."""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if p.exists():
            return p

    env_cfg = os.environ.get("BRIDGE_CONFIG")
    if env_cfg and Path(env_cfg).exists():
        return Path(env_cfg)

    # 1. Рядом с репозиторием (src/bridge_agent_win/../../bridge.toml)
    repo_cfg = Path(__file__).resolve().parent.parent.parent / "bridge.toml"
    if repo_cfg.exists():
        return repo_cfg

    # 2. Рядом с исполняемым файлом
    exe_cfg = Path(sys.executable).parent / "bridge.toml"
    if exe_cfg.exists():
        return exe_cfg

    # 3. В C:\BridgeLocal\bridge.toml
    if sys.platform == "win32":
        std_cfg = Path(r"C:\BridgeLocal\bridge.toml")
        if std_cfg.exists():
            return std_cfg

    # 4. В текущей директории
    cwd_cfg = Path.cwd() / "bridge.toml"
    if cwd_cfg.exists():
        return cwd_cfg

    return None


def show_windows_alert(title: str, message: str, is_error: bool = False) -> None:
    """Показывает нативное системное всплывающее окно Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        flags = (0x10 if is_error else 0x40) | 0x10000 | 0x40000
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    except Exception:
        pass


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


def install_context_menu(
    python_exe: str | None = None,
    drop_script_path: Path | None = None,
) -> bool:
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
        # Проверяем наличие вспомогательного батника drop_to_pocket.bat
        repo_root = Path(__file__).resolve().parent.parent.parent
        drop_bat = drop_script_path
        if drop_bat is None:
            for cand in [
                repo_root / "drop_to_pocket.bat",
                repo_root / "scripts" / "windows" / "drop_to_pocket.bat",
            ]:
                if cand.exists():
                    drop_bat = cand
                    break

        if drop_bat is not None and drop_bat.exists():
            cmd_str = f'"{drop_bat.resolve()}" "%1"'
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
        logger.warning("Удаление контекстного меню через winreg доступна только на Windows.")
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
    show_alert: bool = False,
) -> Path:
    """
    Копирует файл или каталог в локальный Карман для последующей синхронизации.

    Когда файл попадает в Карман, служба Windows (Watchdog) и клиент Linux
    синхронизируют его по локальной сети.
    """
    src = Path(file_path).resolve()
    if not src.exists():
        msg = f"Файл или каталог не найден: {src}"
        if show_alert:
            show_windows_alert("Bridge Local - Ошибка", msg, is_error=True)
        raise FileNotFoundError(msg)

    cfg_file = find_bridge_config(config_path)
    cfg = BridgeConfig.load(cfg_file)

    raw_pocket = Path(cfg.pocket.path).expanduser()
    if raw_pocket.is_absolute():
        pocket_dir = raw_pocket.resolve()
    else:
        # Привязываем относительный путь к каталогу найденного bridge.toml
        base_dir = (
            cfg_file.parent
            if cfg_file
            else (
                Path(__file__).resolve().parent.parent.parent
                if (Path(__file__).resolve().parent.parent.parent / "bridge.toml").exists()
                else Path.cwd()
            )
        )
        pocket_dir = (base_dir / raw_pocket).resolve()

    pocket_dir.mkdir(parents=True, exist_ok=True)
    dest = pocket_dir / src.name

    try:
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
        if show_alert:
            show_windows_alert(
                "Bridge Local - Карман",
                f"Файл '{src.name}' успешно скопирован в Карман!\n\nКаталог: {dest}",
            )
        return dest
    except Exception as e:
        logger.error("[POCKET-DROP-ERROR] Ошибка копирования '%s': %s", src.name, e)
        if show_alert:
            show_windows_alert(
                "Bridge Local - Ошибка",
                f"Ошибка копирования в Карман:\n{e}",
                is_error=True,
            )
        raise


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
        show_alert = sys.platform == "win32" and not sys.stdin.isatty()
        if "--alert" in args:
            show_alert = True
        if "--quiet" in args or "--no-alert" in args:
            show_alert = False
        try:
            dest = drop_file_to_pocket(target, show_alert=show_alert)
            print(f"[OK] Файл отправлен в Карман: {dest}")
        except Exception as e:
            print(f"[ERROR] Сбой отправки в Карман: {e}")
            sys.exit(1)
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
