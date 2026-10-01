# Bridge Local: Engineering & Workflow Guidelines

## 1. Prime Directive: Modularity, Scalability & Cross-Project Reusability
- **Long-Term Foundation:** Bridge Local is engineered not merely as a temporary two-machine bridge, but as a robust, highly extensible, and modular inter-node communication backbone with tremendous future potential.
- **Strict Decoupling & Swappability:** Every architectural layer (`bridge_core`, length-prefix wire framing, JSON-RPC dispatcher, async transport, pocket storage engine, notes engine, executor, security/auth) must remain strictly decoupled with clean abstraction boundaries. Any component must be easily replaceable, upgradeable, or swappable (e.g., alternative transports, different process runners, or pluggable storage backends) without cascading refactors.
- **Portability into Other Projects:** Core modules must be developed as clean, standalone building blocks capable of being extracted, distributed as standalone packages, or directly imported into future projects, distributed automation pipelines, and multi-agent coordination frameworks.
- **Contract-Driven Interfaces:** All inter-layer and inter-node interactions must rely strictly on validated DTO contracts (Pydantic V2) and explicit public interfaces, preventing tightly coupled monolithic dependencies.

## 2. Phased Execution Invariant
- Never launch monolithic multi-agent autonomous builds for the entire project at once.
- Work strictly sequentially, phase by phase, adhering to the phases in `docs/SDLC_PLAN.md`.
- Do not write source code until specifications, contracts, and documentation for the current phase are validated by the user.

## 3. Documentation & Clean Repository Standard
- Maintain consolidated, high-signal documentation strictly under `docs/`.
- Avoid redundant logs, historical devblogs, or repetitive boilerplate. All technical specifications, architectures, and user guides must be up to date and clean.

## 4. Reference Management (ref/)
- `ref/Hum/`: Dedicated to user-supplied references, specifications, UI/CLI concepts, and notes.
- `ref/AI/`: Dedicated to AI-generated technical proposals, architectural diagrams, and analysis for user review and refinement.

## 5. Dev-Mode Hyper-Logging Standard
- During active development, implement comprehensive, granular logging across all layers:
  - Every network packet, RPC call, and heartbeat probe with microsecond timestamps and session IDs.
  - Subprocess execution details (PowerShell PID, arguments, `chcp 65001`, raw stream bytes).
  - File I/O operations and lock attempts in the pocket storage.
- Design logging architecture so this verbose diagnostic trace can be cleanly isolated or disabled for the final Git release via log-level controls (TRACE/DEBUG vs INFO/ERROR) without refactoring business logic.

## 6. Dual Target Persona: Human & AI Operator (agy_cli)
- **Human Ergonomics (Personal Everyday Use):**
  - The CLI and TUI must remain dead-simple for the user's daily life: instant file dropping into the pocket and sending quick text notes/links between Linux and Windows in a single short command without configuration friction.
- **AI Operator Protocol (Antigravity agy_cli Compatibility):**
  - The primary programmatic operator on Linux is the Antigravity CLI agent (`agy_cli`).
  - All commands must support a strict `--json` mode with machine-readable payloads, deterministic exit codes, zero ANSI-escape artifacts, and zero blocking on stdin.
  - Standardized Exit Codes (`bridge_client_linux.exit_codes.ExitCode`):
    - `0` (`SUCCESS`): Command executed successfully.
    - `1` (`GENERAL_ERROR`): Invalid arguments, configuration failure, or internal error.
    - `2` (`NETWORK_ERROR`): Target host unreachable, socket failure, connection refused.
    - `3` (`AUTH_ERROR`): Pre-shared key mismatch, HMAC verification failure, replay detected.
    - `4` (`COMMAND_FAILED`): Remote PowerShell process terminated with non-zero exit code.
    - `5` (`TIMEOUT`): Command execution or RPC response exceeded allotted timeout.
  - Outputs must be token-efficient to minimize LLM context consumption for lightweight models.
- **Future-Proof Extensibility (Multi-Node & Inter-Agent):**
  - All protocol envelopes and DTO models must reserve optional `source_node` and `target_node` fields so that 3+ node mesh routing and Linux `agy_cli` ↔ Windows `agy_cli` cross-account orchestration can be introduced without breaking wire compatibility.

## 7. Terminal UX & Process Activity Animation (At-a-Glance Observability)
- **Minimal, Non-Intrusive In-Progress Animations:**
  - All background operations, active file synchronizations in the pocket, RPC heartbeat probes, and remote PowerShell executions MUST implement minimal, elegant terminal animations (e.g., braille spinners `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`, activity pulse `[>>>]`, or localized progress glyphs).
  - **Operator Goal:** The human operator must be able to glance at the terminal screen from a distance and immediately understand what is actively working, transferring, or waiting, vs what is idle, synced, or errored, without having to read every single line of text or log status.
  - **Zero Flicker Standard:** Terminal animations must be strictly localized to designated glyph placeholders without redrawing the entire screen or causing cursor jump artifacts.
  - **Headless Cleanliness:** When running with `--json` or non-interactive stdout (e.g., invoked by `agy_cli`), all spinner loops and animation escapes must be completely omitted.

## 8. Multi-Node Topology & Modular Scalability (Roadmap F1/F2 Foundation)
- **Zero Two-Node Assumptions:** Code in `bridge_core`, `bridge_client_linux`, and `bridge_agent_win` must never hardcode assumptions that the topology is strictly 1:1.
- **Explicit Addressing:** Every RPC packet carries `source_node` and `target_node`. CLI commands provide `--node / --target` overrides that default to configured target names, ensuring transparent forward-compatibility when node registries or mesh discovery are activated in future phases.
- **Independent Package Extraction:** Packages `bridge_core`, `bridge_client_linux`, and `bridge_agent_win` must be fully independent Python packages with `py.typed` markers, clean imports, and zero circular dependencies, ready to be packaged as standalone wheels or imported into multi-agent systems.

## 9. Git & Release Invariant: Explicit User Approval Only
- **Zero Autonomous Commits, Pushes or Releases:** Agents and subagents must NEVER create git commits, push to remote repositories, create git tags, or publish releases autonomously without explicit user approval or a direct user order.
- **Strict User Authorization Gate:** All code modifications, refactorings, and test creations during a phase remain in the local working tree until the user explicitly commands or confirms a commit and push. No background task or subagent may run `git commit` or `git push` on its own initiative.
