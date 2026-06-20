# Changelog

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
