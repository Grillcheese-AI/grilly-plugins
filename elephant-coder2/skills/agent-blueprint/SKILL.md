---
name: agent-blueprint
description: Design an autonomous agent architecture and execution plan for a goal — capability decomposition, tool orchestration, self-critique loops, success metrics, and failure-mode analysis. Use when the user asks to design, architect, or plan an agent, a multi-step automation, or an autonomous workflow.
---

Produce a concrete, buildable blueprint for an autonomous agent — not a generic
essay. Skip persona preamble; lead with substance.

## When to trigger

- "Design an agent that…", "architect an autonomous workflow for…",
  "plan a multi-step automation that…"
- Any request for an end-to-end agent design with tools, control flow, and metrics.

## Method

1. **Objective & world model.** State the goal precisely, the environment the
   agent acts in, what it can observe, and what "done" means. Call `recall` on the
   goal first — reuse any prior patterns already in memory.
2. **Capability decomposition.** Break the goal into discrete capabilities. For
   each, name the tool/skill that provides it and its inputs/outputs.
3. **Orchestration & control loop.** Specify the loop: plan → act → observe →
   critique → revise. Note where it fans out (parallel subtasks) vs. serializes,
   and the stopping condition.
4. **Self-critique & verification.** Define how each step is checked before being
   trusted (assertions, a verifier, a second pass). State what gets re-tried.
5. **Success metrics.** Give measurable criteria — not "works well" but the signal
   you'd watch and its target.
6. **Failure modes & mitigations.** Enumerate the realistic ways it breaks
   (loops, tool errors, hallucinated state, cost blowups) and the guard for each.
7. **Phased rollout.** Sequence the build: smallest end-to-end slice first, then
   what each later phase adds.

## Output

A structured blueprint covering all seven. Where useful, include pseudocode for
the control loop. Offer to `sidecar_store` the blueprint under a tag so it can be
pulled back later or handed to a subagent.
