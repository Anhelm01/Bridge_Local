"""
bridge_client_linux.tui.screens — Micro/Mini HUD Bridge Local v0.3.0.

Единственный режим интерфейса: компактный MINI HUD (4-5 строк).
  - Статус-строка: узел, пинг, pocket, состояние линка.
  - Строка последней команды / вывода.
  - Строка ввода омнибара.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme
from bridge_core.config import BridgeConfig

# ---------------------------------------------------------------------------
# ANSI цвета
# ---------------------------------------------------------------------------

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_WHITE = "\033[97m"            # Яркий белый
ANSI_YELLOW = "\033[38;2;255;184;0m"   # #FFB800 янтарь
ANSI_RED = "\033[38;2;255;51;102m"    # #FF3366 неоновый коралловый
ANSI_CYAN = "\033[38;2;0;210;255m"    # #00D2FF циан
ANSI_STEEL = "\033[38;2;125;133;144m" # #7D8590 сталь
ANSI_MUTED = "\033[38;2;110;118;129m" # #6E7681 приглушенный

ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def visible_len(text: str) -> int:
    """Длина строки без ANSI escape-последовательностей."""
    return len(ANSI_REGEX.sub("", text))


def format_bytes(num_bytes: int) -> str:
    """Форматирует размер в байтах в читаемый вид."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def get_local_ip() -> str:
    """Определяет активный локальный IP без сетевой блокировки."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = str(s.getsockname()[0])
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_pocket_count(cfg: BridgeConfig) -> int:
    """Считает файлы в локальном кармане."""
    pocket_dir = Path(cfg.pocket.path or "./pocket").expanduser().resolve()
    if not pocket_dir.exists():
        return 0
    count = 0
    for _root, dirs, filenames in os.walk(pocket_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "logs"]
        for fname in filenames:
            if not fname.startswith(".") and not fname.endswith(".part"):
                count += 1
    return count


def get_live_context(custom_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Формирует срез состояния системы для Mini HUD."""
    d = dict(custom_data or {})
    try:
        cfg = BridgeConfig.load()
    except Exception:
        cfg = BridgeConfig()

    tgt_node = d.get("node", {}).get("target") or "WIN-PC"
    tgt_host = (
        d.get("tgt_host")
        or d.get("node", {}).get("host")
        or cfg.connection.host
        or "127.0.0.1"
    )
    tgt_port = d.get("tgt_port") or d.get("node", {}).get("port") or cfg.connection.port or 9732
    tgt_address = d.get("tgt_address") or f"{tgt_host}:{tgt_port}"

    is_online = bool(d.get("is_online", False))
    latency_val = d.get("latency_ms") if is_online else None
    last_error = bool(d.get("last_error", False))
    pocket_count = d.get("pocket_count")
    if pocket_count is None:
        pocket_count = get_pocket_count(cfg)

    return {
        "cfg": cfg,
        "tgt_node": tgt_node,
        "tgt_host": tgt_host,
        "tgt_port": tgt_port,
        "tgt_address": tgt_address,
        "is_online": is_online,
        "latency_val": latency_val,
        "last_error": last_error,
        "pocket_count": int(pocket_count),
        "input_buffer": d.get("input_buffer", ""),
        "status_msg": d.get("status_msg", ""),
        "last_output": d.get("last_output", ""),
        "last_summary": d.get("last_summary", ""),
    }


# ---------------------------------------------------------------------------
# Единственный режим: Mini HUD
# ---------------------------------------------------------------------------

def render_mini_hud(
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Micro/Mini HUD — единственный интерфейс Bridge Local v0.3.0.

    Формат (4-5 строк):
      ┌── BRIDGE LOCAL [MINI] ─────────────────────────────────────────────┐
      │ ● WIN-PC (192.168.100.6:9732) | 4ms | POCKET: Synced (3) | ONLINE │
      │ LAST: [12:31:05] send "report.pdf" -> OK                          │
      └────────────────────────────────────────────────────────────────────┘
        >  █
    """
    ctx = get_live_context(data)
    hud_w = shutil.get_terminal_size((80, 24)).columns
    box_w = max(68, min(hud_w - 2, 120))
    inner_w = box_w - 2

    is_online = ctx["is_online"]
    last_error = ctx["last_error"]
    latency_ms = ctx["latency_val"]
    tgt_node = ctx["tgt_node"]
    tgt_address = ctx["tgt_address"]
    pocket_count = ctx["pocket_count"]

    if last_error:
        state_color = ANSI_YELLOW
        state_dot = f"{ANSI_YELLOW}●{ANSI_RESET}"
        status_tag = f"{ANSI_YELLOW}ERROR{ANSI_RESET}"
    elif is_online:
        state_color = ANSI_RED
        state_dot = f"{ANSI_RED}●{ANSI_RESET}"
        status_tag = f"{ANSI_RED}ONLINE{ANSI_RESET}"
    else:
        state_color = ANSI_STEEL
        state_dot = f"{ANSI_STEEL}○{ANSI_RESET}"
        status_tag = f"{ANSI_STEEL}OFFLINE{ANSI_RESET}"

    lat_str = (
        f"{latency_ms:.0f}ms"
        if (is_online and isinstance(latency_ms, (int, float)))
        else "--"
    )
    pocket_short = f"Synced ({pocket_count})" if is_online else f"Local ({pocket_count})"

    top_title = "── BRIDGE LOCAL [MINI] "
    top_line = (
        ANSI_STEEL + "┌" + top_title + "─" * max(0, inner_w - len(top_title)) + "┐" + ANSI_RESET
    )

    # Row 1 — статус линка
    row1_raw = (
        f" {state_dot} {tgt_node} ({tgt_address})"
        f" | {lat_str}"
        f" | POCKET: {pocket_short}"
        f" | {status_tag}"
    )
    pad1 = max(0, inner_w - visible_len(row1_raw))
    row1 = ANSI_STEEL + "│" + ANSI_RESET + row1_raw + " " * pad1 + ANSI_STEEL + "│" + ANSI_RESET

    # Row 2 — последняя команда
    last_summary = ctx.get("last_summary") or ""
    if not last_summary:
        last_out = ctx.get("last_output") or ctx.get("status_msg") or ""
        clean_first = re.sub(r"\[/?[a-zA-Z0-9_ #]*\]", "", str(last_out)).strip().split("\n")[0]
        last_summary = clean_first or "No commands executed yet"

    row2_raw = f" LAST: {last_summary}"
    if len(row2_raw) > inner_w:
        row2_raw = row2_raw[: inner_w - 3] + "..."
    pad2 = max(0, inner_w - len(row2_raw))
    row2 = ANSI_STEEL + "│" + ANSI_RESET + row2_raw + " " * pad2 + ANSI_STEEL + "│" + ANSI_RESET

    bot_line = ANSI_STEEL + "└" + "─" * inner_w + "┘" + ANSI_RESET

    sys.stdout.write(top_line + "\n")
    sys.stdout.write(row1 + "\n")
    sys.stdout.write(row2 + "\n")
    sys.stdout.write(bot_line + "\n")

    input_line = str(ctx.get("input_buffer", ""))
    sys.stdout.write(f"  {state_color}>{ANSI_RESET}  {ANSI_WHITE}{input_line}{ANSI_RESET}█\n")
    sys.stdout.flush()


def render_current_mode(
    mode: str,
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """Единая точка входа рендеринга — всегда Mini HUD."""
    render_mini_hud(theme, data)
