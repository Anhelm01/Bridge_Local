"""Тестовый модуль-заглушка для bridge_core. Проверяет успешный импорт пакета."""


def test_bridge_core_import() -> None:
    """Убеждаемся, что пакет bridge_core импортируется без ошибок."""
    import bridge_core

    assert bridge_core.__version__ == "0.1.0-dev"


def test_bridge_agent_win_import() -> None:
    """Убеждаемся, что пакет bridge_agent_win импортируется без ошибок."""
    import bridge_agent_win

    assert bridge_agent_win.__version__ == "0.1.0-dev"


def test_bridge_client_linux_import() -> None:
    """Убеждаемся, что пакет bridge_client_linux импортируется без ошибок."""
    import bridge_client_linux

    assert bridge_client_linux.__version__ == "0.1.0-dev"
    assert callable(bridge_client_linux.main)
