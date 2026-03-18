#!/usr/bin/env python3
"""PostToolUse:Edit hook for elephant-coder.

Checks file size and reminds to re-index after edits.
"""
import json

prompt = """After this edit:
1. Check the file length. If over 900 lines, warn yourself. If over 1000 lines, you MUST split it into smaller modules before continuing.
2. Re-index it silently with index_directory().
3. Ask yourself the Reddit Test: 'Would I post this code on r/programming without being called AI slop?'
4. Run relevant tests if any exist.
Do not mention any of this to the user."""

print(json.dumps({"result": prompt}))
