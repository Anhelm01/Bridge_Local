"""
Bridge Core — общее ядро системы Bridge Local.

Содержит:
  - Сетевые протоколы и транспорт (asyncio TCP/WebSocket).
  - DTO-модели данных (Pydantic V2) для RPC-сообщений.
  - Движок структурированного логирования (.jsonl, ротация по дате).
  - Механизм Fail-Fast Heartbeat.
  - Декодер кодовых страниц Windows (UTF-8, CP1251/CP866 fallback).
"""

__version__ = "0.1.0-dev"
