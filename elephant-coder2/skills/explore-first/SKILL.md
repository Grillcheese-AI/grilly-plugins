---
name: explore-first
description: Before writing or editing code in an existing or unfamiliar codebase, survey it first — read the manifest and README, map the structure, learn the conventions, and find reusable code — instead of coding immediately. Use whenever a task means adding to or changing a repo you have not just been working in.
---

Strong agents don't start typing into an unfamiliar repo. They build a model of
it first, so the change fits the project instead of fighting it.

## When to trigger

- About to add a feature, file, or component to an existing codebase.
- Working in a repo (or subtree) you haven't already mapped this session.
- The user says "add it to this project" / "extend X" / "integrate with Y".

## Method

1. **Recall first.** Call `recall` on the task and `recall_file` on any named
   files — reuse what's already in memory before re-reading from scratch.
2. **Read the manifest.** package.json / pyproject.toml / Cargo.toml / go.mod —
   dependencies, scripts, entry points, build/test commands. This tells you how the
   project is meant to be run.
3. **Read the README / docs** for intended structure and conventions.
4. **Map the structure.** List the tree; identify entry points, where similar
   things already live, and the naming/layout patterns to match.
5. **Find reusable code.** Search for existing helpers, patterns, or components
   that already do part of the job — don't duplicate what's there.
6. **Then plan the change** so it matches conventions and reuses what exists.

## Output

A short model of the repo (how it runs, where the change goes, what to reuse),
then the plan. Offer to `sidecar_store` the repo model under a tag so later steps
and subagents don't re-derive it.
