# Спецификация сетевого протокола Bridge_local

Данный документ является нормативным описанием бинарного фрейминга, конвертов криптографической безопасности, схемы сообщений **JSON-RPC 2.0** и каталога удаленных методов платформы **Bridge_local**.

---

## 1. Бинарный фрейминг (Wire Framing)

Взаимодействие между клиентом и агентом осуществляется поверх полнодуплексного асинхронного TCP-соединения (порт по умолчанию: `9732`).

### 1.1. Структура фрейма

Каждый пакет предваряется фиксированным 6-байтовым заголовком:

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
| `0..1` | `MAGIC` | `2 bytes` | Фиксированная последовательность `0x42 0x52` (ASCII: `'BR'`). |
| `2..5` | `PAYLOAD_LEN` | `uint32` (BE) | Длина полезной нагрузки в байтах (Big-Endian). Максимальный размер: `67,108,864` (64 МБ). |
| `6..6+LEN-1`| `PAYLOAD` | `bytes` | Данные сообщения в кодировке UTF-8 (JSON-объект конверта безопасности). |

### 1.2. Валидация заголовка и защита от DoS
1. Если первые 2 байта не равны `0x42 0x52`, соединение немедленно разрывается с генерацией исключения `InvalidMagicError`.
2. Если `PAYLOAD_LEN` превышает `MAX_PAYLOAD_SIZE` (64 МБ), соединение сбрасывается с ошибкой `FrameTooLargeError`.

---

## 2. Конверт безопасности (Security Envelope)

Полезная нагрузка фрейма представляет собой подписанный JSON-объект `SecurityEnvelope`.

```json
{
  "payload": "{\"jsonrpc\":\"2.0\",\"id\":\"9f82...\",\"method\":\"heartbeat.ping\",\"params\":{...}}",
  "nonce": "d2f40b2a-0a75-4c6e-8260-15ef3c5c5679",
  "timestamp": "2026-09-30T20:15:30.123456Z",
  "signature": "3b4f6e8a9d0c..."
}
```

### 2.1. Алгоритм вычисления подписи
Контрольная подпись вычисляется с использованием алгоритма **HMAC-SHA256**:
$$\text{Signature} = \text{HMAC-SHA256}(\text{secret\_key}, \text{timestamp} + ":" + \text{nonce} + ":" + \text{payload})$$
где `secret_key` — общий секрет узлов в кодировке UTF-8.

### 2.2. Защита от Replay-атак (Anti-Replay)
При получении конверта узел выполняет следующие шаги:
1. **Проверка дрейфа времени:** Значение $|T_{\text{local}} - T_{\text{envelope}}| \le \text{clock\_skew\_seconds}$ (по умолчанию 60 сек). При превышении возвращается ошибка `AUTH_FAILED`.
2. **Проверка однократности Nonce:** Значение `nonce` сверяется с циклическим кэшем использованных идентификаторов. При обнаружении дубликата пакет отбрасывается.
3. **Проверка HMAC:** Вычисляется эталонный HMAC. Если подпись не совпадает (константное по времени сравнение `hmac.compare_digest`), пакет отклоняется.

---

## 3. Базовая структура сообщений JSON-RPC 2.0

Внутри поля `payload` передается стандартное сообщение спецификации JSON-RPC 2.0 с опциональными маршрутными полями:

### 3.1. Запрос (Request)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "method": "exec.run",
  "params": { ... },
  "source_node": "linux-workstation",
  "target_node": "windows-agent"
}
```

### 3.2. Успешный ответ (Response)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "result": { ... }
}
```

### 3.3. Ответ с ошибкой (Error Response)
```json
{
  "jsonrpc": "2.0",
  "id": "e8d357f8-3e4d-4ad1-9689-d9d300eb0580",
  "error": {
    "code": -32001,
    "message": "PowerShell command timed out after 30 seconds",
    "data": { ... }
  }
}
```

---

## 4. Коды ошибок протокола

| Код | Символическая константа | Описание |
|:---|:---|:---|
| **`-32700`** | `PARSE_ERROR` | Некорректный JSON в полезной нагрузке пакета. |
| **`-32600`** | `INVALID_REQUEST` | Сообщение не соответствует спецификации JSON-RPC 2.0. |
| **`-32601`** | `METHOD_NOT_FOUND` | Запрошенный метод не зарегистрирован в диспетчере. |
| **`-32602`** | `INVALID_PARAMS` | Ошибка валидации параметров метода (Pydantic ValidationError). |
| **`-32603`** | `INTERNAL_ERROR` | Необработанное внутреннее исключение на стороне сервера. |
| **`-32001`** | `COMMAND_TIMEOUT` | Превышен лимит времени выполнения команды PowerShell. |
| **`-32002`** | `COMMAND_FAILED` | Процесс завершился с ненулевым кодом выхода. |
| **`-32003`** | `AUTH_FAILED` | Ошибка проверки HMAC-подписи, дрейф времени или повтор Nonce. |
| **`-32004`** | `NODE_UNREACHABLE` | Целевой узел недоступен в сети. |
| **`-32005`** | `POCKET_SYNC_ERROR` | Сбой контрольной суммы SHA-256 или ошибка файлового ввода-вывода. |
| **`-32006`** | `FILE_NOT_FOUND` | Запрашиваемый в кармане файл не существует. |

---

## 5. Каталог удаленных методов (RPC Methods)

### 5.1. `heartbeat.ping`
Зонд доступности узла и мониторинг телеметрии.

**Параметры (`PingParams`):**
```json
{
  "client_timestamp_us": 1727727330123456,
  "client_os": "linux"
}
```

**Результат (`PongResult`):**
```json
{
  "agent_timestamp_us": 1727727330125000,
  "agent_os": "windows",
  "cpu_percent": 3.5,
  "memory_used_mb": 4200,
  "uptime_seconds": 182400,
  "status": "ready"
}
```

---

### 5.2. `exec.run`
Выполнение команды в изолированном экземпляре PowerShell на Windows.

**Параметры (`ExecRequestParams`):**
```json
{
  "command": "Get-Process -Name BridgeLocalAgent",
  "timeout_sec": 30,
  "run_as_admin": true,
  "working_dir": null,
  "env": null
}
```

**Результат (`ExecResult`):**
```json
{
  "exit_code": 0,
  "stdout": "Handles  NPM(K)    PM(K)      WS(K)     CPU(s)     Id ProcessName\n-------  ------    -----      -----     ------     -- -----------\n    180      14    25400      38100       0.45   4820 BridgeLocal...\n",
  "stderr": "",
  "duration_ms": 142,
  "started_at": "2026-09-30T20:15:30.100000Z",
  "completed_at": "2026-09-30T20:15:30.242000Z",
  "timed_out": false,
  "encoding_detected": "utf-8"
}
```

---

### 5.3. `pocket.manifest`
Получение списка файлов кармана с контрольными суммами SHA-256.

**Параметры:** пустой объект `{}`.

**Результат (`PocketManifestResult`):**
```json
{
  "files": [
    {
      "path": "docs/architecture.pdf",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size_bytes": 1048576,
      "mtime_iso": "2026-09-30T18:00:00Z"
    }
  ],
  "total_size_bytes": 1048576,
  "file_count": 1
}
```

---

### 5.4. `pocket.push`
Передача чанка данных файла для сохранения в карман.

**Параметры (`PocketPushParams`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "data_b64": "UEsDBBQAAAAIA...",
  "is_last": false,
  "sha256_full": null
}
```
*Примечание: в последнем чанке передается `"is_last": true` и вычисленный `"sha256_full"` для атомарной валидации и переименования из `.part` файла.*

**Результат (`PocketPushResult`):**
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

### 5.5. `pocket.pull`
Чтение чанка файла из удаленного кармана.

**Параметры (`PocketPullParams`):**
```json
{
  "path": "release.zip",
  "offset": 0,
  "chunk_size": 65536
}
```

**Результат (`PocketPullResult`):**
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

### 5.6. `pocket.offset`
Запрос текущего смещения частично загруженного файла для докачки (Resumable Upload/Download).

**Параметры (`PocketOffsetParams`):**
```json
{
  "path": "bigfile.iso"
}
```

**Результат (`PocketOffsetResult`):**
```json
{
  "path": "bigfile.iso",
  "offset": 1310720,
  "part_exists": true,
  "completed": false
}
```

---

### 5.7. `notes.send`
Отправка быстрой текстовой заметки или ссылки.

**Параметры (`NoteSendParams`):**
```json
{
  "text": "https://github.com/Anhelm01/Bridge_Local/pull/1",
  "author_os": "linux",
  "target_node": null
}
```

**Результат (`NoteDeliveryResult`):**
```json
{
  "note_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "received_at": "2026-09-30T20:20:00.123456Z",
  "status": "delivered"
}
```

---

### 5.8. `notes.history`
Запрос истории заметок с фильтрацией по времени и количеству.

**Параметры (`NoteHistoryParams`):**
```json
{
  "limit": 10,
  "since": null
}
```

**Результат (`NoteHistoryResult`):**
```json
{
  "notes": [
    {
      "note_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "timestamp": "2026-09-30T20:20:00.123456Z",
      "author_os": "linux",
      "text": "https://github.com/Anhelm01/Bridge_Local/pull/1",
      "status": "delivered"
    }
  ],
  "total_count": 1
}
```

---

### 5.9. `notes.mark_read`
Квитирование прочтения заметок.

**Параметры (`NoteMarkReadParams`):**
```json
{
  "note_ids": [
    "7c9e6679-7425-40de-944b-e07fc1f90ae7"
  ]
}
```

**Результат (`NoteMarkReadResult`):**
```json
{
  "marked_count": 1
}
```
