"""
Bridge Agent Windows — серверный агент для Windows.

Содержит:
  - Интеграция с Windows Service Manager (SCM).
  - Изолированный раннер PowerShell с повышенными привилегиями.
  - Process Tree Killer (таймаутное завершение зависших процессов).
  - Локальный диспетчер записи логов в «карман».
"""

__version__ = "0.1.0-dev"
