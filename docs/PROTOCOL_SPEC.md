# Спецификация сетевого протокола Bridge Local

Данный документ является нормативным техническим описанием бинарного фрейминга, криптографических конвертов безопасности, схемы сообщений **JSON-RPC 2.0** и каталога удаленных RPC-методов платформы **Bridge Local**.

---

## 1. Бинарный фрейминг (Wire Framing)

Взаимодействие между клиентом и серверным агентом осуществляется поверх полнодуплексного асинхронного TCP-соединения (порт по умолчанию: `9732`).

### 1.1. Структура бинарного фрейма

Каждый пакет данных предваряется фиксированным 6-байтовым бинарным заголовком:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       MAGIC (0x42 0x52 / 'BR')|         PAYLOAD LENGTH        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   PAYLOAD LENGTH (cont.)      |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+                               +
|                                                               |
|                   PAYLOAD BYTES (UTF-8 JSON)                  |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Смещение (байты) | Поле | Тип | Описание |
|:---|:---|:---|:---|
| **`0..1`** | `MAGIC` | `2 bytes` | Фиксированная последовательность `0x42 0x52` (ASCII-строка `'BR'`). |
| **`2..5`** | `PAYLOAD_LEN` | `uint32` (BE) | Длина полезной нагрузки в байтах (Big-Endian unsigned integer). |
| **`6..6+LEN-1`**| `PAYLOAD` | `bytes` | Данные сообщения в кодировке UTF-8 (JSON-RPC 2.0 документ или конверт безопасности). |

### 1.2. Правила валидации фрейма и защита от DoS
1. **Проверка маркера `MAGIC`:** Если первые 2 байта входящего фрейма не равны `0x42 0x52`, соединение немедленно закрывается с генерацией исключения `InvalidMagicError`.
2. **Лимит размера полезной нагрузки:** Если объявленное значение `PAYLOAD_LEN` превышает константу `MAX_PAYLOAD_SIZE = 67_108_864` (64 МБ), соединение сбрасывается с ошибкой `FrameTooLargeError`. Это защищает сервер от атак исчерпания памяти буферов приема.
3. **Обработка фрагментации TCP:** Считывание осуществляется через асинхронный вызов `reader.readexactly(length)`, что гарантирует получение полного пакета даже при дроблении на уровне MTU сетевого адаптера.

---

## 2. Криптографическая аутентификация и защита от Replay-атак

При установленном параметре `connection.psk_token` каждый запрос и ответ защищается криптографической подписью на базе общего секрета (Pre-Shared Key).

### 2.1. Конверт безопасности (Security Envelope)

Полезная нагрузка фрейма упаковывается в JSON-объект `SecurityEnvelope`:

```json
{
  "payload": "{\"jsonrpc\":\"2.0\",\"id\":\"9f82c418-70b1-4f12-9c44-d8a101f3e221\",\"method\":\"heartbeat.ping\",\"params\":{...}}",
  "nonce": "d2f40b2a0a754c6e826015ef3c5c5679",
  "timestamp": "2026-10-01T12:00:00.123456Z",
  "signature": "3b4f6e8a9d0c..."
}
```

### 2.2. Алгоритм вычисления подписи (HMAC-SHA256)
Цифровая подпись пакета формируется алгоритмом **HMAC-SHA256**:
```
Signature = HMAC-SHA256(secret_key, timestamp + ":" + nonce + ":" + payload)
```
где:
- `secret_key` — Pre-Shared Key токен в кодировке UTF-8.
- `timestamp` — время генерации пакета в формате UTC ISO-8601 или эпоха в секундах.
- `nonce` — уникальный криптографический токен (128-битная hex-строка).
- `payload` — сериализованный JSON-документ запроса или ответа.

### 2.3. Алгоритм верификации пакета
При получении фрейма серверный агент выполняет три последовательные проверки:
1. **Проверка дрейфа системного времени (Clock Skew):**
   Разница между локальным системным временем и временем пакета $|T_{\text{local}} - T_{\text{envelope}}|$ не должна превышать допустимый порог (по умолчанию 60 секунд). При превышении пакет отклоняется с кодом ошибки `-32003` (`AUTH_FAILED`).
2. **Проверка однократности Nonce (Anti-Replay Protection):**
   Узел сохраняет полученный `nonce` в кэше с временем жизни, равным максимальному дрейфу часов. При повторном появлении уже зафиксированного `nonce` запрос немедленно отвергается с ошибкой `TokenReplayError`.
3. **Проверка HMAC-подписи:**
   Вычисляется эталонный хэш. Сравнение выполняется функцией постоянного времени `hmac.compare_digest(sig, expected_sig)`, что полностью исключает атаки по времени (Timing Attacks).

---

## 3. Спецификация сообщений JSON-RPC 2.0

Внутри поля `payload` передается сообщение спецификации JSON-RPC 2.0. Платформа расширяет стандарт опциональными полями межмашинной маршрутизации `source_node` и `target_node`.

### 3.1. Структура запроса (Request)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "method": "exec.run",
  "params": {
    "command": "Get-Process -Name BridgeLocalAgent",
    "timeout_sec": 30,
    "run_as_admin": true
  },
  "source_node": "workstation-linux",
  "target_node": "win-agent"
}
```

### 3.2. Структура успешного ответа (Response)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "result": {
    "exit_code": 0,
    "stdout": "BridgeLocalAgent Running\n",
    "stderr": "",
    "duration_ms": 35,
    "started_at": "2026-10-01T12:00:00.000000Z",
    "completed_at": "2026-10-01T12:00:00.035000Z",
    "timed_out": false
  }
}
```

### 3.3. Структура ответа с ошибкой (Error Response)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "error": {
    "code": -32001,
    "message": "PowerShell command timed out after 30 seconds",
    "data": {
      "timed_out": true,
      "timeout_sec": 30
    }
  }
}
```

---

## 4. Коды ошибок протокола (JSON-RPC Error Codes)

Коды ошибок разделены на стандартные коды спецификации JSON-RPC 2.0 и специализированные коды платформы Bridge Local:

| Код ошибки | Символическая константа | Описание |
|:---:|:---|:---|
| **`-32700`** | `PARSE_ERROR` | Некорректный синтаксис JSON в полезной нагрузке пакета. |
| **`-32600`** | `INVALID_REQUEST` | Структура сообщения не соответствует спецификации JSON-RPC 2.0. |
| **`-32601`** | `METHOD_NOT_FOUND` | Запрошенный удаленный метод не зарегистрирован в RPC-диспетчере. |
| **`-32602`** | `INVALID_PARAMS` | Ошибка валидации параметров вызова метода (Pydantic ValidationError). |
| **`-32603`** | `INTERNAL_ERROR` | Необработанное исключение во внутреннем коде серверного обработчика. |
| **`-32001`** | `COMMAND_TIMEOUT` | Превышен лимит времени выполнения команды PowerShell на Windows. |
| **`-32002`** | `COMMAND_FAILED` | Процесс PowerShell завершился с ненулевым кодом выхода. |
| **`-32003`** | `AUTH_FAILED` | Ошибка проверки HMAC-подписи, дрейф системных часов или повтор Nonce. |
| **`-32004`** | `NODE_UNREACHABLE` | Целевой узел недоступен в сети или отклонил сетевое подключение. |
| **`-32005`** | `POCKET_SYNC_ERROR` | Несовпадение контрольной суммы SHA-256 или ошибка файлового ввода-вывода. |
| **`-32006`** | `FILE_NOT_FOUND` | Запрошенный в хранилище кармана файл не найден на диске. |

---

## 5. Каталог удаленных методов (RPC Methods)

### 5.1. Метод `heartbeat.ping`
Периодический зонд доступности узла и передача телеметрии состояния.

**Параметры запроса (`PingParams`):**
```json
{
  "client_timestamp_us": 1727784000123456,
  "client_os": "linux"
}
```

**Результат ответа (`PongResult`):**
```json
{
  "server_timestamp_us": 1727784000125000,
  "server_node": "win-workstation",
  "uptime_seconds": 124800,
  "cpu_percent": 4.2,
  "memory_percent": 38.5,
  "memory_used_mb": 6144,
  "active_connections": 1,
  "status": "ready"
}
```

---

### 5.2. Метод `exec.run`
Выполнение сценария в изолированном экземпляре PowerShell на Windows.

**Параметры запроса (`ExecRequestParams`):**
```json
{
  "command": "Get-Service -Name BridgeLocalAgent",
  "timeout_sec": 30,
  "run_as_admin": true,
  "working_dir": "C:\\BridgeLocal"
}
```

**Результат ответа (`ExecResult`):**
```json
{
  "exit_code": 0,
  "stdout": "Status   Name               DisplayName\n------   ----               -----------\nRunning  BridgeLocalAgent   Bridge Local Agent Daemon\n",
  "stderr": "",
  "duration_ms": 118,
  "started_at": "2026-10-01T12:00:00.000000Z",
  "completed_at": "2026-10-01T12:00:00.118000Z",
  "timed_out": false,
  "encoding_detected": "utf-8"
}
```

---

### 5.3. Метод `pocket.manifest`
Получение полного списка файлов кармана с размерами и контрольными суммами SHA-256 для построения дифференциальной карты синхронизации.

**Параметры запроса:** Пустой объект `{}`.

**Результат ответа (`PocketManifestResult`):**
```json
{
  "files": [
    {
      "path": "docs/architecture.pdf",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size_bytes": 1048576,
      "mtime_iso": "2026-10-01T11:30:00Z"
    }
  ],
  "total_size_bytes": 1048576,
  "file_count": 1
}
```

---

### 5.4. Метод `pocket.push`
Потоковая передача блока данных (чанка) для сохранения файла в кармане.

**Параметры запроса (`PocketPushParams`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "data_b64": "UEsDBBQAAAAIA...",
  "is_last": false,
  "sha256_full": null
}
```
*В последнем чанке передается `"is_last": true` и вычисленный отправителем полный хэш `"sha256_full"`. Сервер валидирует хэш и атомарно перемещает файл из `.part` в целевое имя.*

**Результат ответа (`PocketPushResult`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "bytes_written": 65536,
  "is_last": false,
  "completed": false,
  "sha256": null
}
```

---

### 5.5. Метод `pocket.pull`
Чтение чанка файла из удаленного кармана.

**Параметры запроса (`PocketPullParams`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "chunk_size": 65536
}
```

**Результат ответа (`PocketPullResult`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "data_b64": "UEsDBBQAAAAIA...",
  "is_last": false,
  "total_size_bytes": 524288
}
```

---

### 5.6. Метод `pocket.offset`
Запрос смещения частично полученного файла для возобновления прерванной передачи (Resumable Transfer).

**Параметры запроса (`PocketOffsetParams`):**
```json
{
  "path": "archive.iso"
}
```

**Результат ответа (`PocketOffsetResult`):**
```json
{
  "path": "archive.iso",
  "offset": 1048576,
  "part_exists": true,
  "completed": false
}
```

---

### 5.7. Метод `notes.send`
Мгновенная отправка текстовой заметки или гиперссылки.

**Параметры запроса (`NoteSendParams`):**
```json
{
  "text": "https://github.com/Anhelm01/Bridge_Local",
  "author_os": "linux",
  "target_node": "win-agent"
}
```

**Результат ответа (`NoteDeliveryResult`):**
```json
{
  "note_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "received_at": "2026-10-01T12:00:00.123456Z",
  "status": "delivered"
}
```

---

### 5.8. Метод `notes.history`
Получение журнала переданных и полученных заметок.

**Параметры запроса (`NoteHistoryParams`):**
```json
{
  "limit": 10,
  "since": null
}
```

**Результат ответа (`NoteHistoryResult`):**
```json
{
  "notes": [
    {
      "note_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "timestamp": "2026-10-01T12:00:00.123456Z",
      "author_os": "linux",
      "text": "https://github.com/Anhelm01/Bridge_Local",
      "status": "delivered"
    }
  ],
  "total_count": 1
}
```

---

### 5.9. Метод `notes.mark_read`
Квитирование прочтения заметок по списку их идентификаторов.

**Параметры запроса (`NoteMarkReadParams`):**
```json
{
  "note_ids": [
    "7c9e6679-7425-40de-944b-e07fc1f90ae7"
  ]
}
```

**Результат ответа (`NoteMarkReadResult`):**
```json
{
  "marked_count": 1
}
```
