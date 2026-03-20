---
name: configure
description: Configure elephant-coder project settings interactively (redis, qdrant, framework, paths, API keys)
---

Interactively configure elephant-coder for the current project.

## Steps

1. Load current settings with `update_settings()` (call with no args to see current state), or read `.claude/elephant-coder.local.md` directly.

2. Present the user with the current configuration grouped by category:

   **Storage**
   - Redis URL (default: redis://localhost:6379)
   - Redis TTL
   - Max memories (default: 50000)

   **Vector Search**
   - Qdrant URL (default: None = local numpy fallback)
   - Encoder model (default: all-MiniLM-L6-v2)
   - Enabled (default: true)

   **Project**
   - Framework (default: auto-detect, e.g. "grilly", "django", "react")
   - GitHub repo (e.g. "grillcheese/elephant-coder")
   - Knowledge docs path (default: docs/project_knowledge)
   - Business docs path (default: docs/business)

   **External Validation**
   - OpenRouter API key
   - Model (default: google/gemini-3.1-flash-lite-preview)
   - Enabled (default: false)

3. Ask the user which settings they want to change. Accept one or multiple at a time.

4. For each changed setting, call `update_settings()` with the new value.

5. After all changes, show the updated configuration and confirm it was saved to `.claude/elephant-coder.local.md`.

## Important
- Never show API keys in full — mask them like `sk-or-v1-...3df3c`
- Settings are per-project — stored in `.claude/elephant-coder.local.md`
- Changes take effect on the next tool call (no restart needed)
- For vector search: if Qdrant URL is set, it becomes primary; otherwise local numpy fallback
