# Bridge_local

**Extensible Cross-Platform Inter-Node Orchestration & Communication Platform**  
*Linux ↔ Windows LAN Backbone | Pluggable Layered Architecture | Headless AI Operator & Human TUI*

[![CI](https://github.com/Anhelm01/Bridge_Local/actions/workflows/ci.yml/badge.svg)](https://github.com/Anhelm01/Bridge_Local/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14-00D2FF.svg)
![Tests](https://img.shields.io/badge/tests-286%20passed-00FF66.svg)
![Mypy](https://img.shields.io/badge/mypy-strict-7D8590.svg)
![Ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)
![Architecture](https://img.shields.io/badge/architecture-modular%20platform-blue.svg)

> **Status:** Phase 6 Complete & Hardened [OK] | 286 tests passing (100% green) | Resumable Transfers & Self-Healing ready.

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

## Project Structure

```
Bridge_Local/
├── src/
│   ├── bridge_core/        # Decoupled platform core: protocol framing, async transport,
│   │                       # models, logger, security, codec, pocket engine, notes engine
│   ├── bridge_agent_win/   # Windows service daemon, PowerShell runner, process killer, context menu
│   ├── bridge_client_linux/# Linux CLI client & TUI (Human + agy_cli headless engine)
│   └── bridge_local/       # Main CLI entrypoint (bridge-cli = bridge_local:main)
├── tests/
│   ├── unit/               # Unit and edge-case tests (262 tests)
│   ├── integration/        # Full end-to-end multi-layer tests over TCP loopback
│   └── mocks/              # Mock fixtures for standalone Linux development
├── devblog/                # Engineering reports per phase
├── docs/                   # SDLC plan, architecture, deployment guides
├── ref/
│   ├── Hum/                # Human references (concepts, notes, scripts)
│   └── AI/                 # AI architectural proposals, analyses, logo concepts
├── .github/workflows/      # Cross-platform GitHub Actions CI (Ubuntu + Windows)
└── pyproject.toml          # uv project configuration
```

---

## Development & Testing

```bash
# Install dependencies
uv sync --extra dev --extra linux

# Run full test suite (272 tests)
LD_PRELOAD="" uv run pytest

# Check code formatting and linter
uv run ruff check .
uv run ruff format --check .

# Static type check (strict)
uv run mypy
```

---

## Engineering DevBlog

Follow the step-by-step development journey, technical decisions, and solved challenges in [devblog/](devblog/README.md):
- [Phase 0: Scaffold & Rules](devblog/00_init_and_planning.md)
- [Phase 1: Contracts & DTOs](devblog/phase_01_contracts.md)
- [Phase 2: Bridge Core Library](devblog/phase_02_core.md)
- [Phase 3: Windows Agent & Service Daemon](devblog/phase_03_win_agent.md)
- [Phase 4: Pocket Storage & Notes Subsystem](devblog/phase_04_pocket_notes.md)
- [Phase 4.5: Visual Identity & Titanium Vivid Theme](devblog/phase_04_5_ui_ux_identity.md)
- [Phase 5: Linux Client CLI & TUI](devblog/phase_05_linux_cli.md)
- [QA Audit: Addams Family Stress & Fuzzing](devblog/qa_adam_family_audit.md)
- [Phase 6: Resilience & Self-Healing](devblog/phase_06_resilience.md)
