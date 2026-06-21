---
name: status
description: Show elephant-coder2 memory store statistics for the current project
---

Call the elephant-coder2 `status` tool and present the results:

- Project root and project hash
- Total memories and the per-tier breakdown (scratch / project_durable / global_durable)
- Vector count
- Redis cache status (live or SQLite-only fallback)

If the total is 0, note that the project has not been indexed yet and suggest
running `/elephant-coder2:index`.
