---
name: harden
description: Refactor and harden an existing implementation for production — correctness, memory and concurrency safety, performance, security, observability, and tests. Use when the user asks to harden, productionize, make robust, or review-and-refactor a piece of code for safety or performance.
---

Turn working-but-fragile code into production-ready code. Concrete diffs and
reasoning, not a lecture.

## When to trigger

- "Harden / productionize / make this robust", "refactor for safety/perf",
  "review this implementation for issues before shipping".

## Method

1. **Read it first.** Read the actual code. Call `recall_file` on the path to pull
   anything already known about it. Restate what it does and its invariants.
2. **Correctness.** Find logic errors, edge cases, off-by-ones, unhandled inputs,
   and silent failures. Each finding gets a concrete fix.
3. **Memory & concurrency safety.** Lifetimes/ownership, bounds, leaks, data races,
   lock ordering, reentrancy. Name the specific hazard, not "be careful".
4. **Performance.** Identify the real hot path before optimizing. Call out
   allocations in loops, needless copies, and algorithmic blowups; give the fix and
   its expected effect.
5. **Security.** Input validation, injection surfaces, unsafe deserialization,
   secret handling. (For a full review, defer to the `threat-model` skill.)
6. **Observability.** Errors should surface, not vanish — logging/metrics at the
   right seams.
7. **Tests.** Add tests that would have caught the above: edge cases, failure
   paths, and a regression test per bug fixed.

## Output

A prioritized list of findings, each with severity and a concrete fix, followed by
the hardened implementation. Offer to `remember` any durable invariant or gotcha
discovered so it sticks for next time.
