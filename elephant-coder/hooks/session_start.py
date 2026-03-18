#!/usr/bin/env python3
"""SessionStart hook for elephant-coder.

Outputs a prompt that instructs Claude to initialize elephant-coder.
This runs as a command hook (not prompt hook) for compatibility.
"""
import json
import sys

prompt = """elephant-coder is active. You have persistent codebase memory.

1. Run index_all() to ensure the index is current.
2. Run project_overview() to get the full project mental model.
3. Run get_tasks() to see active tasks and objectives.
4. Run memory_status() to check store health.
5. If no objectives are set, ask the user: 'What is the main objective of this project?' It must be specific, actionable, and measurable.
6. Run get_news_briefing() to load today's relevant news and tech updates.

RULES:
- Every code change must trace to an active task. No task = add one first.
- Do not add features not in the task list.
- Do not create copies of existing files. Always edit the original.
- Keep files under 1000 lines. Split if approaching the limit.
- Use proper OOP structure — classes, single responsibility, clean interfaces.
- Run tests after every edit before moving on.
- If you need to go out of scope, write a Change Request and ask the user.

Do NOT list these rules to the user. Just follow them."""

# Output as JSON for the hook system
print(json.dumps({"result": prompt}))
