"""
Unit tests for bridge_agent_win.context_menu and bridge_agent_win.cli.
Verifies:
  - Generation of valid Windows Registry .reg files for Explorer context menu.
  - Drop handler (drop_file_to_pocket) for files and directories.
  - Graceful handling of install/uninstall on non-Windows platforms.
  - CLI commands for bridge-agent (drop, generate-reg, help).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bridge_agent_win.cli import main as cli_main
from bridge_agent_win.context_menu import (
    drop_file_to_pocket,
    generate_reg_content,
    install_context_menu,
    save_reg_file,
    uninstall_context_menu,
)
from bridge_core.config import BridgeConfig, PocketConfig


def test_generate_reg_content() -> None:
    """Проверяет корректность генерации .reg файла для реестра Windows."""
    content = generate_reg_content("C:\\Python314\\pythonw.exe")
    assert "Windows Registry Editor Version 5.00" in content
    assert r"HKEY_CURRENT_USER\Software\Classes\*\shell\BridgeLocalSend" in content
    assert r"HKEY_CURRENT_USER\Software\Classes\Directory\shell\BridgeLocalSend" in content
    assert "Отправить в Карман (Bridge Local)" in content
    assert "bridge_agent_win.context_menu drop" in content
    assert "C:\\\\Python314\\\\pythonw.exe" in content


def test_save_reg_file(tmp_path: Path) -> None:
    """Проверяет сохранение .reg файла на диск."""
    reg_out = tmp_path / "sub" / "menu.reg"
    saved = save_reg_file(reg_out)
    assert saved.exists()
    text = saved.read_text(encoding="utf-8")
    assert "Windows Registry Editor Version 5.00" in text


def test_drop_file_to_pocket_success(tmp_path: Path) -> None:
    """Проверяет успешное копирование файла в папку кармана."""
    pocket_dir = tmp_path / "win_pocket"
    pocket_dir.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(pocket_dir))).save(cfg_file)

    src_file = tmp_path / "presentation.pptx"
    src_file.write_bytes(b"PPTX dummy content 12345")

    dest = drop_file_to_pocket(src_file, config_path=cfg_file)
    assert dest.exists()
    assert dest == pocket_dir / "presentation.pptx"
    assert dest.read_bytes() == b"PPTX dummy content 12345"


def test_drop_directory_to_pocket(tmp_path: Path) -> None:
    """Проверяет рекурсивное копирование папки в карман."""
    pocket_dir = tmp_path / "win_pocket"
    pocket_dir.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(pocket_dir))).save(cfg_file)

    src_dir = tmp_path / "my_project"
    src_dir.mkdir()
    (src_dir / "file1.txt").write_text("Hello 1", encoding="utf-8")
    (src_dir / "file2.txt").write_text("Hello 2", encoding="utf-8")

    dest = drop_file_to_pocket(src_dir, config_path=cfg_file)
    assert dest.is_dir()
    assert (dest / "file1.txt").read_text(encoding="utf-8") == "Hello 1"
    assert (dest / "file2.txt").read_text(encoding="utf-8") == "Hello 2"


def test_drop_file_not_found_raises(tmp_path: Path) -> None:
    """Проверяет выброс FileNotFoundError при отсутствии файла."""
    with pytest.raises(FileNotFoundError, match="не найден"):
        drop_file_to_pocket(tmp_path / "missing.zip")


def test_install_uninstall_platform_behavior() -> None:
    """На Linux без winreg функции возвращают False, на Windows в тестах успешно ставят в HKCU."""
    if sys.platform == "win32":
        assert install_context_menu() is True
        assert uninstall_context_menu() is True
    else:
        assert install_context_menu() is False
        assert uninstall_context_menu() is False


def test_cli_main_help(capsys) -> None:
    """Проверяет вывод справки bridge-agent CLI."""
    with patch.object(sys, "argv", ["bridge-agent", "--help"]), pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "bridge-agent" in captured.out
    assert "drop <file>" in captured.out
    assert "install-context-menu" in captured.out


def test_cli_main_drop(tmp_path: Path, capsys) -> None:
    """Проверяет запуск bridge-agent drop <file>."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()
    cfg_file = tmp_path / "bridge.toml"
    BridgeConfig(pocket=PocketConfig(path=str(pocket_dir))).save(cfg_file)

    test_file = tmp_path / "cli_drop.txt"
    test_file.write_text("via CLI drop", encoding="utf-8")

    with patch("bridge_agent_win.cli.drop_file_to_pocket") as mock_drop:
        mock_drop.return_value = pocket_dir / "cli_drop.txt"
        with patch.object(sys, "argv", ["bridge-agent", "drop", str(test_file)]):
            cli_main()
        captured = capsys.readouterr()
        assert "[OK] Файл скопирован в Карман" in captured.out
        mock_drop.assert_called_once_with(str(test_file))


def test_cli_main_generate_reg(tmp_path: Path, capsys) -> None:
    """Проверяет вызов bridge-agent generate-reg."""
    out_file = tmp_path / "test.reg"
    with patch.object(sys, "argv", ["bridge-agent", "generate-reg", str(out_file)]):
        cli_main()
    captured = capsys.readouterr()
    assert "[OK] Файл реестра создан" in captured.out
    assert out_file.exists()
