---
name: recent
description: Show recently changed files and their indexed symbols (git-aware)
---

Run `recent_changes(days=7, limit=20)` to show what's been modified recently.

If the user specified a number of days (e.g., `/ec:recent 30`), use that as the `days` parameter.

Present results showing which files changed, their symbols, and whether any memories are stale.
