# Changelog

## [0.6.0] - 2026-06-20

- `preview-check` skill — for visual/runtime deliverables (web/UI/game/render),
  launch a real preview and inspect screenshot + console + ready state before
  claiming it works. The visual specialization of `verify-loop`; mined from the
  Fable traces' `preview_eval`/`screenshot`/`console_logs` loop. 10 skills total.

## [0.5.0] - 2026-06-20

Three agent operating-habit skills, mined from real Claude Fable 5 agentic CoT
traces (cfahlgren1/Fable-5-traces). Where the 0.4.0 six are task templates (what
to produce), these encode how a strong agent works (the Bash/Edit/Read/preview
build-run-observe loop the traces are dominated by).

- `explore-first` — survey an unfamiliar repo (manifest, README, structure,
  reusable code) before editing.
- `verify-loop` — never declare a change done without running it and observing the
  real output; fix-rerun-reobserve.
- `runtime-debug` — when it runs but misbehaves, debug by observing live state
  (logs, console, ready state) and probing one hypothesis, not shotgun edits.

## [0.4.0] - 2026-06-20

Six auto-triggering expert-workflow skills, distilled from the recurring task
archetypes in the Mythos prompt corpus (persona boilerplate stripped; methodology
kept). Each wires into the plugin's own memory tools (`recall`, `recall_file`,
`sidecar_store`, `remember`).

- `agent-blueprint` — autonomous agent architecture + execution plan.
- `harden` — refactor/productionize code (correctness, safety, perf, tests).
- `threat-model` — defensive security analysis + detection-as-code + hardening.
- `proof-trace` — step-by-step proof/derivation with verification.
- `research-proposal` — critique + falsifiable experimental design.
- `expert-brief` — balanced, structured expert analysis with opposing views.

## [0.3.0] - 2026-06-20

Agentic power tools (Fable-inspired memory/retrieval surface). MCP tool count
7 → 14.

- `sidecar_store` / `sidecar_recall` / `sidecar_list` — tag-keyed context offload,
  a complete key-value store (store/recall/list + `forget` to delete). Mirrors
  Fable's artifact persistent-storage API; lets subagents stash findings and the
  main agent pull compact summaries.
- `brief` — a ready-to-paste, token-lean memory brief for a task/subagent.
- `related` — symbol navigation: definitions + every memory whose body references it.
- `recent` — temporal recall (the `recent_chats` analog), newest memories first.
- `forget` — delete a memory by id.
- Store: `SQLiteStore.search_content`, `by_kind`, `recent`.
- Tests: 14 handler tests passing.

Still deferred: the 5 hooks (Fable's real edge — *silent automatic* activation),
the GGUF sidecar (rerank/consolidation), schedule_task, configure.

## [0.2.1] - 2026-06-20

- Slash commands: `/elephant-coder2:index`, `/elephant-coder2:status`,
  `/elephant-coder2:recall` (thin wrappers over the MCP tools).

## [0.2.0] - 2026-06-20

First runnable surface (minimal slice).

- `broker/handlers.py` — `build_handlers(project_root)` wiring the tested store +
  indexers into broker ops: `index_path` (extension dispatch + mtime-skip),
  `recall` (FTS + vector merge, no model rerank yet), `recall_file`,
  `search_symbol`, `remember`, `promote`, `status`, `ping`.
- `mcpd/server.py` — MCP server exposing 7 tools; embeds a BrokerServer thread so
  hooks can later share the same store. (Lives in `mcpd/`, not `mcp/`, to avoid
  shadowing the `mcp` SDK package on sys.path.)
- `broker/__main__.py` — standalone persistent broker entry (`python -m broker`).
- `.mcp.json` — registers the `elephant-coder2` MCP server.
- `tests/test_handlers.py` — 7 handler round-trip tests. Suite: 45 passing.

Deferred (not in this slice): GGUF sidecar (rerank/consolidation), the 5 hooks,
the 20 skills, cross-project global tier, background task queue.

## [0.1.0] - 2026-04-17

- Initial scaffolding
