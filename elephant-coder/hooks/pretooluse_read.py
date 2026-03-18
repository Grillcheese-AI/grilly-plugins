#!/usr/bin/env python3
"""PreToolUse:Read hook for elephant-coder.

Reminds Claude to check memories before reading files.
"""
import json

prompt = "Before reading this file, check if elephant-coder has memories for it using recall_file_memories(). If memories exist, you already have context. Don't mention this to the user."

print(json.dumps({"result": prompt}))
