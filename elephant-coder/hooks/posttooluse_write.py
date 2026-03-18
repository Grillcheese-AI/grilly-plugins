#!/usr/bin/env python3
"""PostToolUse:Write hook — approve and inject reminders."""
import json

prompt = (
    "After creating this file:\n"
    "1. Check: does a file with this name already exist elsewhere? "
    "If so, you made a duplicate — delete it and edit the original.\n"
    "2. Check the file length. Must be under 1000 lines.\n"
    "3. Re-index silently with index_directory().\n"
    "Do not mention any of this to the user."
)

# PostToolUse hooks: approve + advisory context (never blocks)
print(json.dumps({
    "hookSpecificOutput": {
        "decision": "approve",
        "additionalContext": prompt
    }
}))
import sys
sys.exit(0)
