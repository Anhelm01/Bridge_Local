# Bridge Local

Cross-platform LAN inter-node communication backbone: **Linux ↔ Windows**.

> **Status:** Phase 5 Complete ✅ | 177 tests passing | Linux CLI (Human + AI Headless) & TUI ready.

---

## ⚡ Core Capabilities

- **Linux CLI Client (`bridge-cli`):**
  - **Dual Target Persona:** Human Ergonomics (interactive TUI, Neofetch splash) + AI Operator Protocol (`agy_cli` headless `--json`).
  - Standardized deterministic exit codes (0 = Success, 2 = Network Error, 3 = Auth Error, 4 = Command Failed, 5 = Timeout).
  - Terminal Observability: minimal, non-flickering Braille animations (`⠋⠙⠹...`, `[>>>]`) visible from across the room.
  - Official Cyber-Industrial theme: **Titanium Vivid** (`#FFFFFF` Laser White, `#7D8590` Steel, `#00D2FF` Electric Cyan, `#00FF66` Emerald Green, `#FFB800` Amber Gold, `#C084FC` Neon Purple).
- **Pocket (Карман):** Standalone file sharing engine without SMB/Samba, WebDAV, or cloud services.
  - Streaming 64 KB chunk transfers with SHA-256 integrity verification.
  - Atomic temporary `.<filename>.part` writes with `os.replace` promotion.
  - Native filesystem change detection with debouncing (`watchdog`).
  - Bi-directional sync with conflict resolution based on modification timestamps.
- **Notes (Записки):** Fast two-way text/snippet/link sharing between machines.
  - Persistent atomic JSONL storage with time/limit filtering and read status acknowledgments.
- **Remote PowerShell Execution:**
  - Strict UTF-8 console output decoding (`chcp 65001`, `$OutputEncoding`).
  - Process tree killer (`taskkill /F /T`) by configurable timeout without dangling background processes.
- **Windows Service Daemon:**
  - Background system service running before user logon.
  - Fail-fast heartbeat with system health telemetry (CPU, RAM, Uptime).
- **Mandatory Audit Logging:**
  - Atomic JSONL audit trail with daily rotation (`pocket/logs/YYYY-MM-DD.jsonl`) and synchronous `os.fsync`.
- **Future-Proof Multi-Node & Inter-Agent Ready:**
  - Reserved `source_node` and `target_node` routing in all wire protocol envelopes and CLI commands (`--node / --target`) for 3+ device mesh networks and Linux `agy_cli` ↔ Windows `agy_cli` cross-account orchestration.

---

## 🚀 Quick Start (CLI Usage)

```bash
# 1. Full-screen Neofetch splash with BRIDGES Master emblem:
bridge-cli welcome

# 2. Interactive TUI with Drawbridge header & [F1..F6] tabs (DASH, POCKET, NOTES, EXEC, CONFIG, DEV):
bridge-cli tui

# 3. Check node status (Human table vs AI JSON):
bridge-cli status
bridge-cli status --json

# 4. Liveness ping:
bridge-cli ping --count 3 --json

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
```

---

## 📁 Project Structure

```
Bridge_Local/
├── src/
│   ├── bridge_core/        # Decoupled core: protocol framing, async transport, models,
│   │                       # logger, security, codec, pocket engine, notes engine
│   ├── bridge_agent_win/   # Windows service daemon, PowerShell runner, process killer
│   ├── bridge_client_linux/# Linux CLI client & TUI (Human + agy_cli headless engine)
│   └── bridge_local/       # Main CLI entrypoint (bridge-cli = bridge_local:main)
├── tests/
│   ├── unit/               # Unit tests for all individual components & CLI commands
│   ├── integration/        # Full end-to-end multi-layer tests over TCP loopback
│   └── mocks/              # Mock fixtures for standalone Linux development
├── devblog/                # Engineering reports per phase (lively developer diary)
├── docs/                   # SDLC plan, architecture, deployment guides
├── ref/
│   ├── Hum/                # Human references (concepts, notes, scripts)
│   └── AI/                 # AI architectural proposals, analyses, logo concepts
└── pyproject.toml          # uv project configuration
```

---

## 🛠️ Development & Testing

```bash
# Install dependencies
uv sync --extra dev --extra linux

# Run full test suite (177 tests)
LD_PRELOAD="" uv run pytest

# Check code formatting and linter
uv run ruff check
uv run ruff format --check

# Static type check
uv run mypy src tests
```

---

## 📖 Engineering DevBlog

Follow the step-by-step development journey, technical decisions, and solved challenges in the [devblog/](file:///home/anhelm/Projects/Bridge_Local/devblog/README.md):
- [Phase 0: Scaffold & Rules](file:///home/anhelm/Projects/Bridge_Local/devblog/00_init_and_planning.md)
- [Phase 1: Contracts & DTOs](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_01_contracts.md)
- [Phase 2: Bridge Core Library](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_02_core.md)
- [Phase 3: Windows Agent & Service Daemon](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_03_win_agent.md)
- [Phase 4: Pocket Storage & Notes Subsystem](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_04_pocket_notes.md)
- [Phase 4.5: Visual Identity & Titanium Vivid Theme](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_04_5_ui_ux_identity.md)
- [Phase 5: Linux Client CLI & TUI](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_05_linux_cli.md)
