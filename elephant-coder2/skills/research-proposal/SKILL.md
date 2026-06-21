---
name: research-proposal
description: Critique a technical approach and produce a forward-looking, falsifiable research proposal — hypothesis, experimental design with controls and metrics, ablations, risks, and milestones. Use when the user asks to critique research, propose experiments, design a study, or extend a method.
---

Act as a rigorous research collaborator: assess what exists, then propose what to
try next in a way that could actually be falsified.

## When to trigger

- "Critique this approach/paper", "propose experiments for…", "design a study to
  test…", "how would you extend…", "research plan for…".

## Method

1. **State of the art.** Summarize the approach and its central claims fairly. Call
   `recall` for any prior notes on the topic.
2. **Critique.** Strengths, gaps, and unstated assumptions. Separate "wrong" from
   "unproven" from "untested at scale".
3. **Hypothesis.** A specific, testable claim the proposed work would confirm or
   refute. Vague goals don't count.
4. **Experimental design.** Independent/dependent variables, controls, baselines,
   metrics, and the ablations that isolate the effect. Say what result would
   support the hypothesis and what would kill it.
5. **Falsifiability & confounds.** Name the confounds and how the design controls
   for them. If it can't be falsified, redesign it.
6. **Risks & milestones.** Failure modes, resource/time risks, and a milestone
   sequence where each step de-risks the next.

## Output

State of the art → critique → hypothesis → experimental design → falsifiability →
risks & milestones. Offer to `remember` the hypothesis and metrics so progress can
be tracked across sessions.
