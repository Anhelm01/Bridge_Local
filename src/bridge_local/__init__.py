"""
Bridge Local — корневой пакет проекта.

Реэкспортирует точку входа CLI и предоставляет единую версию.
Реальная логика распределена по подпакетам:
  - bridge_core: общее ядро (протокол, транспорт, логирование).
  - bridge_agent_win: серверный агент Windows.
  - bridge_client_linux: клиент CLI Linux.
"""

__version__ = "0.1.0-dev"


def main() -> None:
    """Точка входа bridge-cli (заглушка до Фазы 5)."""
    print(f"bridge-local v{__version__}: CLI is not yet implemented. See docs/SDLC_PLAN.md")
