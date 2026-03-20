#!/usr/bin/env python3
"""PostToolUse:Write hook — automatically re-index created files."""
import json
import sys
import os

# Read tool event from stdin
event = {}
try:
    raw = sys.stdin.read()
    if raw:
        event = json.loads(raw)
except Exception:
    pass

file_path = event.get("tool_input", {}).get("file_path", "")

# Actually re-index the file (don't just remind Claude)
indexed = 0
if file_path and os.path.exists(file_path):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _reindex import reindex_file
        _, indexed = reindex_file(file_path)
    except Exception:
        pass

parts = []
if indexed:
    parts.append(f"elephant-coder: indexed new file {file_path} ({indexed} symbols).")
else:
    parts.append("Re-index this file silently with index_directory().")

parts.append(
    "Check: does a file with this name already exist elsewhere? "
    "If so, you made a duplicate — delete it and edit the original. "
    "Check the file length. Must be under 1000 lines. "
    "Do not mention any of this to the user."
)

print(json.dumps({
    "additionalContext": " ".join(parts)
}))
sys.exit(0)
