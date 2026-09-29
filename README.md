# Bridge Local

Cross-platform remote management & file synchronization utility: Linux → Windows over LAN.

> **Status:** Phase 0 — Architecture, documentation, and project scaffold.

## Features (planned)

- **Pocket (Карман):** Shared file folder with built-in sync engine between Linux and Windows.
- **Notes (Записки):** Two-way text messaging between machines.
- **Remote Exec:** Elevated PowerShell command execution from Linux CLI with configurable timeouts.
- **Windows Service:** Background agent running before user logon.
- **Fail-Fast Heartbeat:** Instant detection of Windows node unavailability.
- **AI-Ready CLI:** Headless mode with JSON output and deterministic exit codes.

## Project Structure

```
Bridge_Local/
├── src/
│   ├── bridge_local/       # Root package (CLI entrypoint)
│   ├── bridge_core/        # Shared core: protocol, transport, logging
│   ├── bridge_agent_win/   # Windows service agent
│   └── bridge_client_linux/# Linux CLI client
├── tests/
│   ├── unit/               # Unit tests
│   ├── integration/        # E2E and integration tests
│   └── mocks/              # Mock Windows agent for Linux-only testing
├── docs/                   # SDLC plan, deployment guides
├── devblog/                # Engineering reports per phase
├── ref/
│   ├── Hum/                # Human references (design, requirements)
│   └── AI/                 # AI analysis and proposals
└── pyproject.toml          # uv project config
```

## Development

```bash
# Install dependencies
uv sync --extra dev --extra linux

# Run tests
uv run pytest

# Run CLI stub
uv run bridge-cli
```

## License

TBD
