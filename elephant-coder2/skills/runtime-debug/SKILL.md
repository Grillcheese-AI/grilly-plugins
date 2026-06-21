---
name: runtime-debug
description: When code runs but misbehaves — a hang, crash, blank or garbled output, or wrong result — debug by observing live state rather than guessing. Gather evidence (logs, exit codes, console, ready state, intermediate values), form one hypothesis, probe it, then change one thing. Use for any "it runs but does the wrong thing" situation.
---

The thing executes but the result is wrong. Don't shotgun-edit — find out what's
actually happening, then fix the real cause.

## When to trigger

- Output is wrong, blank, garbled, hanging, or intermittently failing.
- A screenshot/test/run times out or returns something unexpected.
- You're tempted to "try changing something and see" — stop and debug instead.

## Method

1. **Reproduce.** Get a reliable trigger. If it's intermittent, find the conditions.
2. **Gather evidence before theorizing.** Read logs, exit codes, console output,
   ready/health state, and intermediate values. For a UI/render hang: is the page
   loaded (readyState), is the element present, is the loop actually advancing, are
   there console errors? Let the evidence narrow it, not a guess.
3. **One hypothesis.** State the single most likely cause given the evidence.
4. **Probe it cheaply.** Confirm or kill the hypothesis with a targeted check — a
   print, an eval, a log line — *before* editing code. Most guesses die here.
5. **Change one thing.** Fix the confirmed cause only. Don't bundle speculative fixes.
6. **Re-observe.** Run again and verify the symptom is gone (hand off to `verify-loop`).
   If not, the hypothesis was wrong — back to the evidence, not more edits.

## Output

Evidence → hypothesis → probe result → the single fix → re-observation. If the
root cause isn't found yet, say what the evidence rules in and out rather than
applying a speculative patch.
