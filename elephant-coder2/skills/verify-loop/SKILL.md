---
name: verify-loop
description: Don't declare a code change done until you've actually run it and observed the result — build/run/test, read the real output and exit code, compare to expected, then refine. Use after making any change that can be executed, or whenever a task needs a verified working result rather than plausible-looking code.
---

Evidence before assertions. A change that hasn't been run isn't done — it's a
hypothesis. Close the loop by observing the real result.

## When to trigger

- Just made an edit/wrote code that can be compiled, run, or tested.
- About to claim something "works", "is fixed", or "passes".
- The user asks to build something and see it working, not just written.

## Method

1. **Smallest runnable change.** Make one coherent change, not ten, before checking.
2. **Run it.** Build, execute, or run the test — the real command, not a dry read.
3. **Observe the actual result.** Read the exit code, stdout/stderr, test output,
   or rendered result. Quote what actually happened; don't assume the happy path.
4. **Compare to expected.** Does the observed result match the intent? If not,
   the gap is the next thing to fix.
5. **Fix and repeat.** Change one thing, re-run, re-observe. Avoid editing blind.
6. **Lock it in.** Add or update a test that would catch this regressing.

## Output

State what you ran, what you observed (the real output), and whether it matched —
then the next change. Never report success without having run the thing. If you
couldn't run it, say so explicitly rather than implying it passed.
