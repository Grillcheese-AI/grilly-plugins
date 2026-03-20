---
name: persona
description: Manage AI personas — add, edit, select, set default persona for conversations
---

Manage AI personas that define how Claude behaves in this project.

## What is a Persona?

A persona is a set of instructions that shape Claude's behavior, tone, and expertise.
Personas are stored in `.claude/personas/` as markdown files with YAML frontmatter.

## Usage

- `/ec:persona` — show current persona and list available ones
- `/ec:persona list` — list all available personas
- `/ec:persona add <name>` — create a new persona interactively
- `/ec:persona edit <name>` — edit an existing persona
- `/ec:persona select <name>` — switch to a persona for this session
- `/ec:persona default <name>` — set the default persona (used on session start)

## Persona File Format

Each persona is stored at `.claude/personas/<name>.md`:

```markdown
---
name: Senior Backend Engineer
description: Deep systems expertise, concise, pragmatic
default: false
tone: direct
expertise:
  - systems programming
  - distributed systems
  - performance optimization
---

You are a senior backend engineer with 15+ years of experience.
You value correctness over cleverness, and simplicity over abstraction.
You always consider edge cases, concurrency issues, and performance implications.
When reviewing code, you focus on: error handling, resource leaks, and API design.
```

## Steps

### List personas
1. Glob `.claude/personas/*.md`
2. Parse YAML frontmatter from each
3. Show name, description, and whether it's the default
4. Show which persona is currently active (if any)

### Add a persona
1. Ask the user for:
   - Name (used as filename)
   - Description (one line)
   - Tone (direct, friendly, formal, casual)
   - Areas of expertise
   - Full system prompt (the persona's instructions)
2. Write to `.claude/personas/<name>.md` with YAML frontmatter
3. Ask if it should be the default

### Edit a persona
1. Read the existing persona file
2. Show current content
3. Ask what to change
4. Update the file

### Select a persona
1. Read the persona file
2. Inject its content as context for the current session using `remember()` with kind="note"
3. Confirm: "Persona '<name>' active for this session"

### Set default
1. Read all persona files
2. Set `default: false` on all
3. Set `default: true` on the selected one
4. Save all files
5. The default persona's content is loaded via the SessionStart hook

## Integration

The SessionStart hook should check for a default persona at `.claude/personas/` and inject
its instructions as additional context. This makes the persona active automatically.

## Built-in Personas

If no personas exist, offer to create these starters:
- **default** — Standard Claude behavior (no modifications)
- **senior-engineer** — Deep technical expertise, code-review focused
- **architect** — System design, patterns, trade-offs
- **mentor** — Teaching-oriented, explains reasoning, suggests learning
