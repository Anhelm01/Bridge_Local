"""
bridge_client_linux.exit_codes — Детерминированные коды завершения CLI для ИИ-агентов (agy_cli).

Стандартизирует коды завершения bridge-cli для программных вызовов
через инструмент run_command в Antigravity и других агентных системах:
  0: Успешное выполнение
  1: Общая ошибка (неверные аргументы, сбой конфигурации, локальный сбой)
  2: Сетевая ошибка (Connection refused, хост недоступен, сбой сокета)
  3: Ошибка аутентификации (неверный PSK токен, сбой HMAC подписи, Replay attack)
  4: Ошибка выполнения удалённой команды (процесс завершился с ненулевым кодом)
  5: Таймаут (превышен лимит времени выполнения команды или ответа RPC)
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Детерминированные коды завершения CLI."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    NETWORK_ERROR = 2
    AUTH_ERROR = 3
    COMMAND_FAILED = 4
    TIMEOUT = 5
