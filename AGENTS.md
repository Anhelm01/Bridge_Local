# Bridge Local: Engineering & Workflow Guidelines

## 1. Phased Execution Invariant
- Never launch monolithic multi-agent autonomous builds for the entire project at once.
- Work strictly sequentially, phase by phase, adhering to the phases in `docs/SDLC_PLAN.md`.
- Do not write source code until specifications, contracts, and documentation for the current phase are validated by the user.

## 2. Mandatory Reporting (devblog/)
- Upon completing any phase or sub-phase, create a comprehensive engineering report in `devblog/` (e.g. `devblog/phase_01_contracts.md`).
- The report must document: objectives, deliverables, dev-logging added, test results, edge cases identified, and readiness checklist.

## 3. Reference Management (ref/)
- `ref/Hum/`: Dedicated to user-supplied references, specifications, UI/CLI concepts, and notes.
- `ref/AI/`: Dedicated to AI-generated technical proposals, architectural diagrams, and analysis for user review and refinement.

## 4. Dev-Mode Hyper-Logging Standard
- During active development, implement comprehensive, granular logging across all layers:
  - Every network packet, RPC call, and heartbeat probe with microsecond timestamps and session IDs.
  - Subprocess execution details (PowerShell PID, arguments, `chcp 65001`, raw stream bytes).
  - File I/O operations and lock attempts in the pocket storage.
- Design logging architecture so this verbose diagnostic trace can be cleanly isolated or disabled for the final Git release via log-level controls (TRACE/DEBUG vs INFO/ERROR) without refactoring business logic.
