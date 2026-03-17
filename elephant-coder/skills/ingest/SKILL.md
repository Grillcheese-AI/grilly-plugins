---
name: ingest
description: Ingest documents from project knowledge or papers directories
---

Run `ingest_knowledge` for the user's document directories:

1. `ingest_knowledge(path='docs/official_papers')` — research papers (PDF, MD)
2. `ingest_knowledge(path='docs/project_knowledge')` — uploaded reference docs

If the user specified a custom path after `/ec:ingest`, use that path instead.

Report how many documents and entries were processed.
