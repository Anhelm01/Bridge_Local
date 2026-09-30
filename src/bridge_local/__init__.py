"""
Bridge Local — корневой пакет проекта.

Реэкспортирует точку входа CLI и предоставляет единую версию.
Реальная логика распределена по подпакетам:
  - bridge_core: общее ядро (протокол, транспорт, логирование, карман, записки).
  - bridge_agent_win: серверный агент и служба Windows (PowerShell runner, process killer).
  - bridge_client_linux: клиент CLI/TUI для Linux (интерактивный режим + headless agy_cli).
"""

__version__ = "0.1.0"


def main() -> None:
    """Точка входа bridge-cli."""
    from bridge_client_linux.cli import run

    run()
