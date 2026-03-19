#!/usr/bin/env python3
"""SessionStart hook for elephant-coder."""
import json
import sys

prompt = (
    "elephant-coder is active. You have persistent codebase memory.\n\n"
    "1. Run index_all() to ensure the index is current.\n"
    "2. Run project_overview() to get the full project mental model.\n"
    "3. Run get_tasks() to see active tasks and objectives.\n"
    "4. Run memory_status() to check store health.\n"
    "5. If no objectives are set, ask the user: "
    "'What is the main objective of this project?' "
    "It must be specific, actionable, and measurable.\n"
    "6. Run get_news_briefing() to load today's relevant news.\n\n"
    "RULES:\n"
    "- Every code change must trace to an active task.\n"
    "- Do not add features not in the task list.\n"
    "- Do not create copies of existing files. Always edit the original.\n"
    "- Keep files under 1000 lines.\n"
    "- Run tests after every edit before moving on.\n"
    "- If you need to go out of scope, write a Change Request.\n\n"
    "Do NOT list these rules to the user. Just follow them."
)

print(json.dumps({
    "additionalContext": prompt
}))
sys.exit(0)
