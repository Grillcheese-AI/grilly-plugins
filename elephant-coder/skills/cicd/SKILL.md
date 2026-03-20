---
name: cicd
description: Configure CI/CD pipelines — GitHub Actions, pre-commit hooks, automated testing, deployment
---

Set up or manage CI/CD for the current project. Detects the project type and
generates appropriate pipeline configuration.

## Usage

- `/ec:cicd` — show current CI/CD status and suggest setup
- `/ec:cicd init` — generate CI/CD config based on detected project type
- `/ec:cicd status` — check pipeline status via GitHub API
- `/ec:cicd add <step>` — add a step to the pipeline (e.g. lint, test, deploy)

## Steps

### 1. Detect project type
Use elephant-coder memory and `project_overview()` to determine:
- Language(s): Python, TypeScript, C++, etc.
- Build system: setuptools, npm, CMake, etc.
- Test framework: pytest, jest, ctest, etc.
- Package manager: pip/uv, npm/yarn/pnpm, etc.
- Framework: from `project.framework` setting or auto-detect
- GitHub repo: from `project.github_repo` setting

### 2. Check existing CI/CD
Look for:
- `.github/workflows/*.yml` — GitHub Actions
- `.gitlab-ci.yml` — GitLab CI
- `Jenkinsfile` — Jenkins
- `.circleci/config.yml` — CircleCI
- `pyproject.toml [tool.pytest]` — test config
- `.pre-commit-config.yaml` — pre-commit hooks

### 3. Generate or update pipeline

#### For Python projects
Generate `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run pytest
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run ruff check .
      - run: uv run ruff format --check .
```

#### For TypeScript/Node projects
Generate `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm test
      - run: npm run lint
```

#### For C++/CMake projects
Generate `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cmake -B build -DCMAKE_BUILD_TYPE=Release
      - run: cmake --build build
      - run: ctest --test-dir build
```

### 4. Pre-commit hooks (optional)
Offer to generate `.pre-commit-config.yaml` with:
- Linting (ruff, eslint, clang-format)
- Formatting checks
- Type checking (mypy, tsc)
- Commit message validation

### 5. Deployment (if applicable)
If `project.github_repo` is set:
- Offer PyPI publish workflow for Python packages
- Offer npm publish workflow for Node packages
- Offer Docker build/push for containerized apps

### 6. Track as task
After generating config, create an elephant-coder task to track CI/CD setup.

## GitHub Status Check
If `project.github_repo` is configured, check recent workflow runs:
```bash
gh run list --repo <repo> --limit 5
```

## Notes
- Always use `uv` for Python projects (user preference)
- Respect existing CI config — update rather than replace
- Keep pipelines minimal — only what's needed
- Add caching steps for dependencies when appropriate
