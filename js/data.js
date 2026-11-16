export const PRODUCTS = [
  {
    index: 0,
    count: '01',
    id: 'bridge-local',
    title: 'Bridge Local',
    version: 'v0.3.0',
    category: 'Core P2P Transport',
    accent: '#00d2ff',
    summary: 'Прямой двунаправленный мост между рабочей станцией Linux и ПК на Windows по локальной сети (LAN) или Bluetooth (PAN/RFCOMM) без облаков, флешек и внешних серверов.',
    metrics: [
      { label: 'Задержка LAN', value: '1.8 мс' },
      { label: 'Шифрование', value: 'AES-256-GCM' },
      { label: 'Чанк Кармана', value: '256 КБ + SHA256' },
      { label: 'Архитектура', value: 'Dual-Role Peer' }
    ],
    features: [
      'Общий «Карман» (pocket/) с потоковой передачей, докачкой .part и событийным Watchdog без нагрузки на CPU',
      'Симметричный удалённый запуск: PowerShell (UTF-8 chcp 65001) с Linux и Bash с Windows (bridge-agent exec)',
      'Нативный установщик setup.exe для Windows: служба SCM, иконка в трее, меню Проводника и Toast-уведомления',
      'Двойной интерфейс: терминальный Mini HUD (4–5 строк) для человека и детерминированный --json (коды 0..5) для ИИ'
    ],
    repoPath: '~/Projects/Bridge_Local'
  },
  {
    index: 1,
    count: '02',
    id: 'bridge-macro',
    title: 'Bridge Macro',
    version: 'RPi 3B Gateway',
    category: 'Hardware Micro-Gateway',
    accent: '#ff3366',
    summary: 'Превращает плату Raspberry Pi 3B в автономный аппаратный пульт управления ПК по патч-корду RJ45. На целевой компьютер не нужно устанавливать никакого ПО (100% Agentless через OpenSSH).',
    metrics: [
      { label: 'Целевой ПК', value: 'Agentless SSH' },
      { label: 'Точка Wi-Fi', value: '192.168.4.1 AP' },
      { label: 'Авто-возврат AP', value: '35 сек Watchdog' },
      { label: 'Веб-пульт', value: 'FastAPI + HTMX' }
    ],
    features: [
      'Прямое подключение кабелем RJ45 (eth0 раздаёт DHCP 192.168.10.100 с принудительным отключением EEE-сна)',
      'Собственная Wi-Fi сеть Bridge-Macro с мгновенным открытием Captive Portal на смартфоне или планшете',
      'Любой скрипт .sh или .ps1 в папке macros/ автоматически становится кнопкой быстрого запуска на экране телефона',
      'Режим SSH Bastion (ProxyJump) для прямого подключения IDE ИИ-агентов (Antigravity, Cursor, Claude Code) к целевому ПК'
    ],
    repoPath: '~/Projects/Bridge_Macro'
  },
  {
    index: 2,
    count: '03',
    id: 'bridge-mcp',
    title: 'Bridge MCP Server',
    version: 'MCP Protocol',
    category: 'AI Agent Integration',
    accent: '#a855f7',
    summary: 'Сервер Model Context Protocol (bridge-mcp), предоставляющий автономным ИИ-агентам типизированные инструменты, ресурсы и промпты для управления удалёнными машинами Windows и Linux.',
    metrics: [
      { label: 'Инструменты', value: '11 MCP Tools' },
      { label: 'Ресурсы', value: 'bridge://status' },
      { label: 'Изоляция сокетов', value: 'LD_PRELOAD=""' },
      { label: 'Стек запуска', value: 'Python 3.12 + uv' }
    ],
    features: [
      'Полная телеметрия и диагностика: bridge_ping (RTT, CPU, RAM) и bridge_status + ресурс bridge://pocket/manifest',
      'Безопасный запуск процессов: bridge_exec для команд и асинхронный bridge_start_process для GUI-приложений без таймаута',
      'Файловые операции для ИИ: bridge_send_file, bridge_pull_file, bridge_fs_list и поиск по маске bridge_fs_find',
      'Автоматический сброс LD_PRELOAD="" на старте для защиты локального LAN-трафика от перехвата proxychains'
    ],
    repoPath: '~/Projects/Bridge_MCP'
  },
  {
    index: 3,
    count: '04',
    id: 'bridge-wh',
    title: 'Bridge WH (WinHelper)',
    version: 'Addon wh.*',
    category: 'Security & Diagnostics',
    accent: '#00f5d4',
    summary: 'Модульный плагин-расширение и комплекс технического обслуживания Windows: освобождает гигабайты кэша, вычисляет скрытые майнеры и управляет Windows Defender через RPC wh.*.',
    metrics: [
      { label: 'RPC Префикс', value: 'wh.* Addon' },
      { label: 'Безопасность', value: 'Dry-Run + Retention' },
      { label: 'Эвристика', value: 'Stratum & CPU Scan' },
      { label: 'Интеграция', value: 'Local + Macro' }
    ],
    features: [
      'Глубокая очистка кэшей (%TEMP%, Crash Dumps, WER, Prefetch, CBS, SoftwareDistribution, браузерные и dev-кэши)',
      'Многослойный детектор скрытых криптомайнеров (xmrig, ethminer, phoenixminer), аномалий CPU и пулов stratum',
      'Безопасное управление статусом и исключениями Windows Defender (Add-MpPreference) для папок разработки',
      'Plug & Play подключение в addons/ (Bridge Local) и веб-интерфейс /wh (Bridge Macro) без правок ядра'
    ],
    repoPath: '~/Projects/Bridge_WH'
  }
];

export const TOPOLOGY_ROUTES = [
  {
    id: 'p2p-lan',
    title: '1. Прямой P2P Мост (Bridge Local)',
    protocol: 'TCP 9732 (AEAD AES-256-GCM) + UDP 9735 Discovery',
    accent: '#00d2ff',
    activeNodes: ['linux', 'windows'],
    activeLinks: ['link-lan'],
    packetLabel: "'BE' Frame • HKDF • 256KB Chunks",
    description: 'Linux-станция и Windows-ПК общаются напрямую по гигабитной LAN или Bluetooth PAN. Оба узла равноправны (Dual-Role Peer): общий Карман синхронизируется за миллисекунды, команды PowerShell и Bash летают в обе стороны.'
  },
  {
    id: 'rpi-captive',
    title: '2. Автономный пульт со смартфона (Bridge Macro)',
    protocol: 'Wi-Fi 192.168.4.1 (Captive Portal) ➔ RJ45 eth0 192.168.10.1 (OpenSSH)',
    accent: '#ff3366',
    activeNodes: ['phone', 'rpi', 'windows', 'linux'],
    activeLinks: ['link-wifi', 'link-eth-win', 'link-eth-lin'],
    packetLabel: 'HTMX Macro Trigger ➔ AsyncSSH',
    description: 'Смартфон подключается к точке доступа Bridge-Macro на Raspberry Pi 3B. Экран управления всплывает автоматически (Captive Portal). Нажатие кнопки запускает .ps1 или .sh макрос на целевом ПК по патч-корду RJ45 без какого-либо софта на самом ПК.'
  },
  {
    id: 'ai-mcp',
    title: '3. Управление через ИИ-Агента (Bridge MCP + SSH Bastion)',
    protocol: 'MCP stdio (LD_PRELOAD="") ➔ TCP 9732 / SSH ProxyJump',
    accent: '#a855f7',
    activeNodes: ['ai', 'linux', 'rpi', 'windows'],
    activeLinks: ['link-mcp', 'link-lan', 'link-bastion', 'link-eth-win'],
    packetLabel: 'bridge_exec / bridge_send_file (--json)',
    description: 'Google Antigravity, Cursor или Claude Desktop вызывает типизированные инструменты Bridge MCP (или идёт через SSH ProxyJump малинки), получая чистый JSON со строгими кодами возврата 0..5.'
  },
  {
    id: 'wh-security',
    title: '4. Ревизия и защита узла (Bridge WH Addon)',
    protocol: 'RPC wh.diagnostics / wh.clean / wh.security_scan',
    accent: '#00f5d4',
    activeNodes: ['linux', 'rpi', 'windows'],
    activeLinks: ['link-lan', 'link-eth-win'],
    packetLabel: 'RPC wh.* ➔ Defender & Miner Heuristic',
    description: 'Плагин Bridge_WH вызывается через Addon Engine с Linux-узла или с веб-пульта Raspberry Pi, проводит эвристическое сканирование процессов и сокетов на майнеры и очищает гигабайты временного кэша Windows.'
  }
];

export const TERMINAL_COMMANDS = {
  ping: {
    cmd: 'bridge-cli ping',
    tuiOutput: [
      '┌── BRIDGE LOCAL [MINI] ─────────────────────────────────────────────────────┐',
      '│ ● WIN-PC (192.168.100.6:9732) | 1.6ms | POCKET: Synced (4) | AEAD: ACTIVE  │',
      '│ LAST: ✓ [ping] 4/4 packets, 0% loss, clock skew +12ms                      │',
      '└────────────────────────────────────────────────────────────────────────────┘',
      'PONG from WIN-PC (Windows 11 Pro 23H2) • RTT: 1.62 ms • CPU: 8.4% • RAM: 41%'
    ],
    jsonOutput: {
      status: 'ok',
      exit_code: 0,
      node: 'WIN-PC',
      address: '192.168.100.6:9732',
      transport: 'BE_AEAD_AES256_GCM',
      rtt_ms: 1.62,
      clock_skew_ms: 12,
      telemetry: { os: 'Windows 11 Pro', cpu_percent: 8.4, ram_percent: 41.2, pocket_files: 4 }
    }
  },
  exec: {
    cmd: 'e Get-Service -Name BridgeLocalAgent',
    tuiOutput: [
      '┌── BRIDGE LOCAL [MINI] ─────────────────────────────────────────────────────┐',
      '│ ● WIN-PC (192.168.100.6:9732) | 1.8ms | POCKET: Synced (4) | AEAD: ACTIVE  │',
      '│ LAST: ✓ [exec] exit 0 (48ms, UTF-8 chcp 65001)                             │',
      '└────────────────────────────────────────────────────────────────────────────┘',
      'Status   Name               DisplayName',
      '------   ----               -----------',
      'Running  BridgeLocalAgent   Bridge Local Symmetric P2P Service'
    ],
    jsonOutput: {
      status: 'ok',
      exit_code: 0,
      command: 'Get-Service -Name BridgeLocalAgent',
      encoding: 'utf-8 (chcp 65001)',
      duration_ms: 48,
      remote_exit_code: 0,
      stdout: 'Running  BridgeLocalAgent  Bridge Local Symmetric P2P Service'
    }
  },
  pocket: {
    cmd: 'pocket status',
    tuiOutput: [
      '┌── BRIDGE LOCAL [MINI] ─────────────────────────────────────────────────────┐',
      '│ ● WIN-PC (192.168.100.6:9732) | 1.5ms | POCKET: Watchdog Active            │',
      '│ LAST: ✓ [pocket status] 4 files synced (chunk_size=256KB)                  │',
      '└────────────────────────────────────────────────────────────────────────────┘',
      '  [SYNCED]  release_v0.3.0.zip       14.2 MB   sha256:9f84a2...c10b',
      '  [SYNCED]  sysinfo_report.md        18.4 KB   sha256:3c71e0...88a4',
      '  [SYNCED]  screenshot_clip.png     842.0 KB   sha256:7d12b9...4f21',
      '  [NOTES ]  .notes/notes.jsonl        4.1 KB   12 entries'
    ],
    jsonOutput: {
      status: 'ok',
      exit_code: 0,
      watcher: 'active_event_driven',
      chunk_size_kb: 256,
      files: [
        { name: 'release_v0.3.0.zip', size_bytes: 14889779, sha256: '9f84a2...c10b', state: 'synced' },
        { name: 'sysinfo_report.md', size_bytes: 18841, sha256: '3c71e0...88a4', state: 'synced' },
        { name: 'screenshot_clip.png', size_bytes: 862208, sha256: '7d12b9...4f21', state: 'synced' }
      ]
    }
  },
  wh: {
    cmd: 'call wh.diagnostics --json',
    tuiOutput: [
      '┌── BRIDGE LOCAL [ADDON: wh.*] ──────────────────────────────────────────────┐',
      '│ ● WIN-PC | Addon: Bridge_WH v0.2.0 | Security & Maintenance Engine         │',
      '│ LAST: ✓ [call wh.diagnostics] exit 0                                       │',
      '└────────────────────────────────────────────────────────────────────────────┘',
      '✓ Miner Heuristics : CLEAN (0 suspicious processes, 0 stratum sockets)',
      '✓ Reclaimable Cache: 6.42 GB found in %TEMP%, WER, CrashDumps, CBS',
      '✓ Windows Defender : RealTimeProtection=True (Dev exclusions: 2 paths)',
      '✓ Disk Health      : NVMe C: 412 GB free | Pending Reboot: False'
    ],
    jsonOutput: {
      status: 'ok',
      exit_code: 0,
      addon: 'wh',
      method: 'wh.diagnostics',
      result: {
        miner_scan: { clean: true, suspicious_pids: [], stratum_connections: 0 },
        cleaner_preview_gb: 6.42,
        defender_active: true,
        pending_reboot: false,
        free_space_gb: { C: 412.5, D: 890.1 }
      }
    }
  },
  doctor: {
    cmd: 'bridge-cli doctor',
    tuiOutput: [
      '┌── BRIDGE LOCAL [DOCTOR DIAGNOSTICS] ───────────────────────────────────────┐',
      '│ [PASS] Python Runtime      : 3.13.1 (Pydantic v2, Cryptography AEAD)       │',
      '│ [PASS] Config & PSK Token  : bridge.toml valid (HKDF SHA-256 derived)      │',
      '│ [PASS] Socket Isolation    : LD_PRELOAD="" (proxychains bypass verified)   │',
      '│ [PASS] TCP 9732 / UDP 9735 : Reachable, peer handshake completed in 1.7ms  │',
      '└────────────────────────────────────────────────────────────────────────────┘'
    ],
    jsonOutput: {
      status: 'ok',
      exit_code: 0,
      checks: {
        python_runtime: '3.13.1',
        config_valid: true,
        ld_preload_cleared: true,
        tcp_9732_reachable: true,
        udp_9735_discovery: true,
        aead_handshake_ms: 1.7
      }
    }
  }
};

export const QUICKSTART_TABS = [
  {
    id: 'linux',
    label: 'Linux (CLI & Демон)',
    badge: 'Bridge Local',
    description: 'Запуск интерактивной панели управления start.sh или настройка за 30 секунд через интерактивный мастер:',
    code: `# 1. Интерактивная консоль управления (5 разделов)
./start.sh

# 2. Или прямой запуск через CLI-мастер и самодиагностику
bridge-cli wizard          # Поиск узла по UDP 9735 и генерация PSK-токена
bridge-cli doctor          # Проверка портов 9732/9735, AEAD и хранилища
bridge-cli up              # Поднятие моста и вход в терминальный Mini HUD

# 3. Повседневные команды
bridge-cli send archive.zip --clipboard
bridge-cli exec "Get-Process | Sort-Object CPU -Descending | Select -First 5"`
  },
  {
    id: 'windows',
    label: 'Windows 10/11 (setup.exe)',
    badge: 'Win Agent + Tray',
    description: 'Графический установщик сам настраивает правила брандмауэра, службу Windows SCM, иконку в трее и меню Проводника:',
    code: `:: Вариант А: Графический установщик (рекомендуется)
BridgeLocal-Setup.exe

:: Вариант Б: Портативный запуск из консоли
start.bat
:: Нажмите [1] START BRIDGE LOCAL — запустится служба и иконка в трее
:: Нажмите [2] PAIRING WIZARD — настройка LAN или Bluetooth PAN

:: Выполнение команд с Windows на Linux:
bridge-agent exec "uname -a && systemctl --user status bridge-local"`
  },
  {
    id: 'rpi',
    label: 'Raspberry Pi 3B (Macro)',
    badge: 'Hardware Gateway',
    description: 'Развёртывание автономной точки доступа Wi-Fi с Captive Portal, DHCP-сервера eth0 и обоих сторожевых демонов:',
    code: `# Установка в 1 команду на Raspberry Pi OS Bookworm / Trixie
git clone https://github.com/your-username/Bridge_Macro.git /opt/bridge-macro
cd /opt/bridge-macro
sudo bash scripts/install.sh

# Управление режимом Wi-Fi и проверка кабельного линка
sudo wifi-ap                        # Автономный хотспот Bridge-Macro (192.168.4.1)
sudo wifi-connect "Home_WiFi" "Pass" # Режим клиента домашнего роутера
bridge-wifi-watchdog.sh --status    # Авто-возврат AP через 35 с при потере роутера
check-lan.sh                        # Диагностика eth0 (192.168.10.1) и EEE off`
  },
  {
    id: 'mcp',
    label: 'Antigravity & Cursor MCP',
    badge: 'AI Agents',
    description: 'Конфигурация сервера Bridge MCP и прозрачного SSH-бастиона для автономных ИИ-агентов:',
    code: `// ~/.gemini/config/mcp_config.json (или .cursor/mcp.json)
{
  "mcpServers": {
    "bridge": {
      "command": "uv",
      "args": [
        "run", "--directory", "/home/anhelm/Projects/Bridge_MCP",
        "bridge-mcp", "--config", "/home/anhelm/Projects/Bridge_Local/bridge.toml"
      ],
      "env": { "LD_PRELOAD": "" }
    }
  }
}

# ~/.ssh/config (Для подключения ИИ через аппаратный Bridge Macro)
Host bridge-macro-target
    HostName 192.168.10.100
    User targetuser
    ProxyJump pi@192.168.4.1`
  }
];
