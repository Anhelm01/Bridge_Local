# Bridge Local

Cross-platform LAN inter-node communication backbone: **Linux ↔ Windows**.

> **Status:** Phase 4 Complete ✅ | 146 tests passing | Modular Core, Windows Service, Pocket Sync & Notes ready.

---

## ⚡ Core Capabilities

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
- **Dual Target Persona:**
  - **Human Ergonomics:** Instant one-liner file drops and text sending without configuration friction.
  - **AI Operator Protocol (`agy_cli`):** Headless `--json` mode with deterministic exit codes, token-efficient compact payloads, and zero blocking on stdin.
- **Future-Proof Multi-Node & Inter-Agent Ready:**
  - Reserved `source_node` and `target_node` routing in all wire protocol envelopes for 3+ device mesh networks and Linux `agy_cli` ↔ Windows `agy_cli` cross-account orchestration.

---

## 📁 Project Structure

```
Bridge_Local/
├── src/
│   ├── bridge_core/        # Decoupled core: protocol framing, async transport, models,
│   │                       # logger, security, codec, pocket engine, notes engine
│   ├── bridge_agent_win/   # Windows service daemon, PowerShell runner, process killer
│   ├── bridge_client_linux/# Linux CLI client & TUI (Phase 5)
│   └── bridge_local/       # Main CLI entrypoint
├── tests/
│   ├── unit/               # Unit tests for all individual components
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

# Run full test suite (146 tests)
LD_PRELOAD="" uv run pytest

# Check code formatting and linter
uv run ruff check
uv run ruff format --check
```

---

## 📖 Engineering DevBlog

Follow the step-by-step development journey, technical decisions, and solved challenges in the [devblog/](file:///home/anhelm/Projects/Bridge_Local/devblog/README.md):
- [Phase 0: Scaffold & Rules](file:///home/anhelm/Projects/Bridge_Local/devblog/00_init_and_planning.md)
- [Phase 1: Contracts & DTOs](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_01_contracts.md)
- [Phase 2: Bridge Core Library](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_02_core.md)
- [Phase 3: Windows Agent & Service Daemon](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_03_win_agent.md)
- [Phase 4: Pocket Storage & Notes Subsystem](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_04_pocket_notes.md)
