---
name: proof-trace
description: Work a math or algorithm problem with an explicit step-by-step reasoning trace or rigorous proof sketch — stated assumptions, justified derivation, edge-case checks, and verification. Use for proofs, derivations, correctness or complexity arguments, and hard quantitative problems.
---

Show the reasoning, justified at each step — not just an answer. Rigor over
flourish.

## When to trigger

- "Prove…", "derive…", "show that…", "what's the complexity/closed form of…",
  "solve this rigorously", "reasoning trace for…".

## Method

1. **Restate & assume.** Restate the problem precisely. List given assumptions,
   definitions, and what counts as a valid answer (exact, asymptotic, sketch).
2. **Strategy.** Name the approach (induction, contradiction, construction,
   reduction, case split) and why it fits, before diving in.
3. **Derive step by step.** Each step states what it does and why it's valid.
   Don't skip the step that's actually load-bearing.
4. **Check base & edge cases.** Verify the boundaries the argument depends on
   (n=0/1, empty, degenerate, overflow points).
5. **Verify.** Sanity-check the result independently — a small instance, a
   dimensional/limit check, or a counterexample search that fails.
6. **State limits.** Be explicit about where the argument is a sketch rather than a
   complete proof, and what would be needed to close the gap.

## Output

Assumptions → strategy → justified derivation → checks → result, with the
informal/rigorous boundary called out honestly. Never present a hand-wave as a
proof.
