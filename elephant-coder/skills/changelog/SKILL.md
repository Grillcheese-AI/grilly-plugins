---
name: changelog
description: Update CHANGELOG.md before committing — always run this before creating a git commit to document what changed
---

**MANDATORY**: Before every git commit, update CHANGELOG.md with the changes being committed.

## When to Trigger

This skill MUST be used:
- Before any `git commit`
- Before any `/commit` slash command
- When the user says "commit", "save changes", or "push"
- When you are about to create a commit as part of any workflow

Do NOT skip this step. Every commit must have its changes documented.

## Steps

### 1. Analyze staged changes
Run `git diff --cached --stat` and `git diff --cached` to understand:
- Which files were added, modified, or deleted
- What the actual code changes are
- Whether this is a feature, fix, refactor, docs change, etc.

### 2. Determine the change category
Classify each change into one of:
- **Added** — new features, files, commands, tools
- **Changed** — modifications to existing behavior
- **Fixed** — bug fixes
- **Removed** — deleted features or code
- **Security** — security-related changes
- **Dependencies** — dependency additions or updates

### 3. Read current CHANGELOG.md
Read the file to understand the current format and find the right insertion point.

### 4. Update CHANGELOG.md
If the changes belong to the current `[Unreleased]` or latest version section:
- Append entries under the appropriate category headers
- Keep entries concise — one line per change, starting with the component name in bold

If no `[Unreleased]` section exists and changes are small:
- Add entries under the current version's categories

Format:
```markdown
### Added
- **component**: Brief description of what was added

### Changed
- **component**: Brief description of what changed

### Fixed
- **component**: Brief description of what was fixed
```

### 5. Proceed with commit
After CHANGELOG.md is updated, proceed with the commit as normal.
Include CHANGELOG.md in the staged files.

## Rules

- Keep entries concise — one line per logical change
- Lead with the component/module name in bold
- Use present tense ("Add" not "Added" in the description text)
- Group related changes into a single entry
- Don't document trivial changes (typo fixes, whitespace)
- Don't duplicate — check if the change is already documented
- Match the existing style in the file
