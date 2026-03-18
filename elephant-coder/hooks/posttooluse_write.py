#!/usr/bin/env python3
"""PostToolUse:Write hook for elephant-coder.

Checks for duplicate files and file size after creates.
"""
import json

prompt = """After creating this file:
1. Check: does a file with this name already exist elsewhere? If so, you made a duplicate — delete it and edit the original instead.
2. Check the file length. Must be under 1000 lines.
3. Re-index silently with index_directory().
4. Ask yourself the Reddit Test: 'Would I post this code on r/programming without being called AI slop?'
Do not mention any of this to the user."""

print(json.dumps({"result": prompt}))
