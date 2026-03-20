---
name: git-versioning
description: Enforce git versioning best practices automatically — conventional commits, semantic versioning, changelog updates, branch hygiene. Configurable per project.
---

**ALWAYS ACTIVE**: This skill enforces git versioning best practices automatically.
Claude must follow these rules for every git operation unless the user explicitly overrides.

## Automatic Enforcement

These rules apply automatically. Do NOT ask the user about them unless clarification
is needed for a specific situation.

### 1. Conventional Commits

Every commit message MUST follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat` — new feature (bumps MINOR)
- `fix` — bug fix (bumps PATCH)
- `docs` — documentation only
- `style` — formatting, no code change
- `refactor` — code change that neither fixes nor adds
- `perf` — performance improvement
- `test` — adding or fixing tests
- `build` — build system or dependencies
- `ci` — CI/CD changes
- `chore` — maintenance, no production code change

**Scope** is optional but recommended — use the module/component name:
```
feat(vector-store): add Qdrant backend with project bucketing
fix(retriever): handle empty FTS results in RRF merge
docs(changelog): add v0.3.0 release notes
```

**Breaking changes** — add `!` after type or `BREAKING CHANGE:` in footer:
```
feat(api)!: rename recall() parameter from store to memory_store
```

### 2. Semantic Versioning

Follow [SemVer](https://semver.org/) — `MAJOR.MINOR.PATCH`:
- **MAJOR** — breaking changes (incompatible API changes)
- **MINOR** — new features (backwards-compatible)
- **PATCH** — bug fixes (backwards-compatible)

When to bump (check `pyproject.toml` and `plugin.json`):
- `feat` commits → suggest MINOR bump
- `fix` commits → suggest PATCH bump
- `feat!` or `BREAKING CHANGE` → suggest MAJOR bump
- Multiple types → use highest bump level

Ask the user before bumping the version. Show what the new version would be.

### 3. Changelog Updates

**MANDATORY before every commit:**
1. Run `/ec:changelog` or manually update CHANGELOG.md
2. Add entries under the appropriate version/category
3. Stage CHANGELOG.md with the commit

### 4. Branch Hygiene

When creating branches:
- Use `<type>/<short-description>` naming: `feat/vector-search`, `fix/redis-primary`
- Keep branches focused — one feature/fix per branch
- Suggest squash-merge for feature branches with many small commits

When on `main`:
- For trivial changes (typos, single-line fixes): commit directly
- For non-trivial changes: suggest creating a branch first
- Ask the user if unsure

### 5. Pre-commit Checks

Before creating any commit:
1. ✅ Update CHANGELOG.md
2. ✅ Verify commit message follows conventional format
3. ✅ Check if version bump is needed (for `feat`/`fix`)
4. ✅ Ensure no sensitive files are staged (.env, credentials, API keys)
5. ✅ Run tests if available and the change is non-trivial

## Configuration

These rules can be configured per project in `.claude/elephant-coder.local.md`:

```yaml
git_versioning:
  conventional_commits: true      # enforce conventional commit format
  auto_changelog: true            # always update CHANGELOG.md before commits
  suggest_version_bump: true      # suggest semver bumps on feat/fix
  branch_naming: true             # enforce branch naming convention
  protect_main: true              # suggest branches for non-trivial main changes
  require_tests_before_commit: false  # run tests before every commit
```

All options default to `true` except `require_tests_before_commit`.

## When to Ask the User

- "Should I bump the version?" — after feat/fix commits
- "This is a non-trivial change on main. Create a branch?" — when committing directly to main
- "The commit message doesn't follow conventional format. Adjust?" — if user provides non-standard message
- "These files may contain secrets: <files>. Exclude from commit?" — if .env or key files are staged

## Integration with Other Skills

- `/ec:changelog` — called automatically before commits
- `/ec:cicd` — conventional commits enable automated version bumping in CI
- `/ec:second-opinion` — consider requesting review for breaking changes
