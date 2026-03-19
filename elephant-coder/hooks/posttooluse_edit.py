#!/usr/bin/env python3
"""PostToolUse:Edit hook — inject reminders after edits."""
import json
import sys

prompt = (
    "After this edit:\n"
    "1. Check the file length. If over 900 lines, warn yourself. "
    "If over 1000 lines, you MUST split it into smaller modules.\n"
    "2. Re-index it silently with index_directory().\n"
    "3. Run relevant tests if any exist.\n"
    "Do not mention any of this to the user."
)

print(json.dumps({
    "additionalContext": prompt
}))
sys.exit(0)
