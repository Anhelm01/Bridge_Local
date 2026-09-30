"""
bridge_client_linux.tui.theme — Официальная тема оформления Titanium Vivid.

Определяет единую цветовую спецификацию Cyber-Industrial:
авиационный титан и сталь с ультра-яркими функциональными акцентами.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaletteTheme:
    """Спецификация цветовой палитры терминального интерфейса."""

    name: str
    desc: str
    primary: str  # Главный цвет (логотип Master, акценты, титановый белый)
    secondary: str  # Вторичный цвет (логотип Industrial, стальные фермы, разделители)
    text: str  # Основной яркий белый текст
    muted: str  # Приглушенный цвет
    border: str  # Цвет контуров панелей
    blue: str  # Электрический ультра-циан (сеть, Linux, шина, ссылки)
    green: str  # Лазерный изумрудный (ONLINE, SYNCED, OK)
    amber: str  # Сочный янтарно-золотой (Карман, активная передача)
    purple: str  # Яркий неоновый фиолетовый (Windows-узел, PowerShell, Daemon)
    red: str  # Неоновый коралловый (ошибки, оффлайн)


# Единая утверждённая тема Bridge Local
OFFICIAL_THEME = PaletteTheme(
    name="Titanium Vivid / Cyber-Industrial",
    desc="Единая тема: авиационный титан и сталь с ультра-яркими акцентами",
    primary="#FFFFFF",  # Чистый лазерный белый титан
    secondary="#7D8590",  # Холодная индустриальная сталь
    text="#FFFFFF",  # Предельная четкость белого текста
    muted="#6E7681",  # Читаемый приглушенный
    border="#7D8590",  # Стальной контур
    blue="#00D2FF",  # Электрический ультра-циан (#00D2FF)
    green="#00FF66",  # Лазерный зеленый фосфор (#00FF66)
    amber="#FFB800",  # Сочный янтарно-золотой (#FFB800)
    purple="#C084FC",  # Яркий неоновый фиолетовый (#C084FC)
    red="#FF3366",  # Неоновый коралловый (#FF3366)
)
