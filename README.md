# Bridge_local

**Extensible Cross-Platform Inter-Node Orchestration & Communication Platform**  
*Linux ↔ Windows LAN Backbone | Pluggable Layered Architecture | Headless AI Operator & Human TUI*

[![CI](https://github.com/Anhelm01/Bridge_Local/actions/workflows/ci.yml/badge.svg)](https://github.com/Anhelm01/Bridge_Local/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14-00D2FF.svg)
![Tests](https://img.shields.io/badge/tests-311%20passed-00FF66.svg)
![Mypy](https://img.shields.io/badge/mypy-strict-7D8590.svg)
![Ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)
![Architecture](https://img.shields.io/badge/architecture-modular%20platform-blue.svg)

> **Status:** Phase 7 Complete & Deployed [OK] | 311 tests passing (100% green) | Wheel Packaging & Windows SCM Service Ready.

---

## Architectural Platform Overview

`Bridge_local` is engineered not merely as a point-to-point utility, but as a robust, highly extensible, and modular inter-node communication platform designed for long-term scalability.

### Core Architectural Principles

- **Strict Decoupling & Swappability:** Every architectural layer (`bridge_core`, length-prefix wire framing, JSON-RPC dispatcher, async transport, pocket storage engine, notes engine, process executor, security/auth) is strictly decoupled with clean abstraction boundaries. Any component can be replaced or upgraded (alternative transports, different process runners, pluggable storage backends) without cascading refactors.
- **Portability into Other Projects:** Core modules (`bridge_core`) are developed as clean, standalone building blocks capable of being extracted, distributed as standalone packages, or directly imported into distributed automation pipelines and multi-agent coordination frameworks.
- **Contract-Driven Interfaces:** All inter-layer and inter-node interactions rely strictly on validated DTO contracts (Pydantic V2) and explicit public interfaces, preventing tightly coupled monolithic dependencies.
- **Forward-Compatible Multi-Node Topology:** Wire protocol envelopes and DTO models explicitly carry `source_node` and `target_node` routing fields. This enables 3+ device mesh topologies and cross-account agent orchestration without breaking wire compatibility.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BRIDGE_LOCAL PLATFORM                           │
├─────────────────────┬──────────────────────────────────────────────────┤
│ Security Layer      │ HMAC-SHA256, Nonce Replay Cache, Clock Skew Sync │
│ Wire Protocol       │ 6-byte Magic Framing ('BR'), Length-Prefix Codec │
│ Transport & RPC     │ Asyncio TCP Streaming, JSON-RPC 2.0 Dispatcher   │
│ Execution Engine    │ PowerShell Runner, Process Tree Killer, UTF-8    │
│ Pocket Storage      │ 64 KB Chunk Streaming, SHA-256 Verify, Atomic    │
│ Notes Subsystem     │ Persistent JSONL Engine, Filter & Acknowledgment │
│ Operator Layer      │ Human TUI (Titanium Vivid) + AI Headless --json  │
└─────────────────────┴──────────────────────────────────────────────────┘
```

---

## Core Platform Subsystems

### 1. Linux CLI & AI Operator Interface (`bridge-cli`)
- **Dual Target Persona:**
  - **Human Ergonomics:** Interactive TUI with `[F1..F6]` / `Tab` navigation, localized non-flickering Braille animations (`⠋⠙⠹...`, `[>>>]`), and Neofetch splash.
  - **AI Operator Protocol (`agy_cli`):** Fully deterministic `--json` output, zero ANSI-escape artifacts, non-blocking execution, and standardized exit codes:
    - `0` (`SUCCESS`): Command executed successfully.
    - `1` (`GENERAL_ERROR`): Invalid arguments or internal failure.
    - `2` (`NETWORK_ERROR`): Connection refused or host unreachable.
    - `3` (`AUTH_ERROR`): Pre-shared key mismatch or replay detected.
    - `4` (`COMMAND_FAILED`): Remote execution terminated with non-zero exit code.
    - `5` (`TIMEOUT`): Command execution or RPC response timed out.

### 2. Pocket Storage Engine (Карман)
- Standalone peer-to-peer file synchronizer without SMB, Samba, WebDAV, or cloud dependencies.
- Streaming 64 KB chunk transfers with SHA-256 integrity verification.
- Atomic temporary `.<filename>.part` staging with atomic `os.replace` promotion.
- Native filesystem change detection with debouncing (`watchdog`).
- Direct file send command (`bridge-cli send <file1> [file2...]`) and Windows Explorer right-click integration.

### 3. Notes Subsystem (Записки)
- Rapid two-way text, snippet, and link exchange between nodes.
- Persistent atomic JSONL storage with time/limit filtering and read status acknowledgments.

### 4. Remote Execution Engine (PowerShell)
- Strict UTF-8 console output decoding (`chcp 65001`, `$OutputEncoding`).
- Recursive process tree termination (`taskkill /F /T`) by timeout without lingering background processes.

### 5. Windows Service Daemon
- Background system daemon running before user logon.
- Real-time heartbeat probes with system health telemetry (CPU, RAM, Uptime).
- Daily rotating atomic JSONL audit trail (`pocket/logs/YYYY-MM-DD.jsonl`) with synchronous `os.fsync`.

---

## Quick Start (CLI Usage)

```bash
# 1. Full-screen Neofetch splash with BRIDGES Master emblem:
bridge-cli welcome

# 2. Interactive TUI with Drawbridge header & [F1..F6] tabs (DASH, POCKET, NOTES, EXEC, CONFIG, DEV):
bridge-cli tui

# 3. Check node status (Human table vs AI JSON):
bridge-cli status
bridge-cli status --json

# 4. Fast Direct File Drop (send any file to Windows Pocket):
bridge-cli send ~/Downloads/archive.zip photo.png

# 5. Remote PowerShell command execution:
bridge-cli exec "Get-Service -Name BridgeLocalAgent" --json

# 6. Pocket storage operations:
bridge-cli pocket status --json
bridge-cli pocket push /path/to/archive.zip --json
bridge-cli pocket pull document.pdf --json
bridge-cli pocket sync --direction both --json

# 7. Fast notes sharing:
bridge-cli note send "https://github.com/project/spec" --json
bridge-cli note list --limit 10 --json
bridge-cli note read <note_id> --json

# 8. Windows Explorer Context Menu:
# Right-click any file/folder in Windows Explorer to drop directly into Pocket.
bridge-agent install-context-menu    # Register right-click menu in HKCU
bridge-agent drop <file_or_dir>      # CLI drop helper
```

---

## Packaging & Production Deployment

For complete, step-by-step production setup, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### 1. Linux Client Installation
```bash
# Option A: Isolated user-level CLI tool via uv (recommended):
uv tool install .

# Option B: Install from built wheel:
pip install dist/bridge_local-0.1.0-py3-none-any.whl
```

### 2. Windows Agent & SCM Service Deployment
```powershell
# Automated installation: SCM registration, Defender exclusions, Search Indexing disabling, Firewall rule:
powershell -ExecutionPolicy Bypass -File .\scripts\install-service.ps1 -Port 9732

# Verify service status:
Get-Service -Name BridgeLocalAgent

# Graceful uninstallation and cleanup:
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-service.ps1
```

---

## Project Structure

```
Bridge_Local/
├── src/
│   ├── bridge_core/        # Decoupled platform core: protocol framing, async transport,
│   │                       # models, logger, security, codec, pocket engine, notes engine
│   ├── bridge_agent_win/   # Windows service daemon, PowerShell runner, process killer, context menu
│   ├── bridge_client_linux/# Linux CLI client & TUI (Human + agy_cli headless engine)
│   └── bridge_local/       # Main CLI entrypoint (bridge-cli = bridge_local:main)
├── scripts/                # Production deployment and service administration scripts
│   ├── install-service.ps1 # Automated Windows SCM service installation & hardening
│   ├── uninstall-service.ps1 # Graceful SCM service teardown & rule cleanup
│   ├── build-windows-agent.ps1 # PyInstaller standalone EXE builder
│   └── systemd/            # Linux systemd service unit templates
├── tests/
│   ├── unit/               # Unit, packaging, and edge-case tests
│   ├── integration/        # Full end-to-end multi-layer tests over TCP loopback
│   └── mocks/              # Mock fixtures for standalone Linux development
├── docs/                   # Full documentation suite, architecture, and guides
├── ref/
│   ├── Hum/                # Human references (concepts, notes, scripts)
│   └── AI/                 # AI architectural proposals, analyses, logo concepts
├── bridge-agent.spec       # PyInstaller standalone executable specification
├── .github/workflows/      # Cross-platform GitHub Actions CI (Ubuntu + Windows)
└── pyproject.toml          # uv project configuration & wheel build backend
```

---

## Development & Testing

```bash
# Install dependencies
uv sync --all-extras

# Run full test suite
LD_PRELOAD="" uv run pytest

# Check code formatting and linter
uv run ruff check .
uv run ruff format --check .

# Static type check (strict)
uv run mypy
```

---

## Documentation Portal & Developer Guides

Complete documentation for developers, operators, and systems engineers is available in [docs/](docs/README.md):

- [**Developer Onboarding Guide (Step-by-Step for Humans)**](docs/DEV_GUIDE_FOR_HUMANS.md): Plain-language, zero-friction setup, daily CLI workflow, dev-mode logging, and troubleshooting.
- [**Deployment & Administration Guide**](docs/DEPLOYMENT.md): Windows SCM Service daemon, Windows Defender exclusions, Firewall, and systemd units.
- [**Architecture & Layer Isolation**](docs/ARCHITECTURE.md): Deep platform architecture, DTO contracts, state machines, and multi-node routing.
- [**Wire Protocol & RPC Specification**](docs/PROTOCOL_SPEC.md): Binary framing ('BR' header), HMAC-SHA256 envelopes, and complete JSON-RPC 2.0 catalog.
- [**Configuration Reference (bridge.toml)**](docs/CONFIGURATION.md): Exhaustive breakdown of all settings, resolution cascade, and environment variables.
- [**CLI & TUI Reference Manual**](docs/CLI_REFERENCE.md): Full command reference for `bridge-cli` and `bridge-agent`, deterministic exit codes, and `--json` format.
- [**Developer Standards & Contributing**](docs/DEVELOPMENT.md): Testing with loopback, quality gates (ruff/mypy), and adding new RPC handlers.



