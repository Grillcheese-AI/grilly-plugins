---
name: second-opinion
description: Get a second opinion from an external AI model before implementing features or fixes — reduces implementation risk by exploring all options
---

Before implementing a new feature or bug fix, get a structured second opinion from an
external AI model via OpenRouter. This reduces implementation risk by:

1. Identifying blind spots in the proposed approach
2. Exploring alternative implementation strategies
3. Flagging potential issues (performance, security, compatibility)
4. Suggesting edge cases to consider

## When to Use

This skill should be triggered:
- Before implementing any non-trivial feature
- Before fixing complex bugs
- When there are multiple possible approaches
- When the change affects shared/core code
- When ensemble mode is active (auto-triggered)

## Steps

### 1. Gather context
Collect the following from elephant-coder memory:
- `recall_memories()` for relevant existing code context
- `get_tasks()` for the active task being worked on
- `get_dependencies()` for files that will be affected
- `show_call_graph()` for symbols that will be modified

### 2. Build the review request
Create a structured plan document:

```
## Feature/Bug: <title>
## Task: <task-id>

### Current State
<what exists today, from elephant-coder memory>

### Proposed Approach
<the implementation plan>

### Files to Modify
<list of files and what changes>

### Dependencies Affected
<from call graph and dependency analysis>

### Questions for Reviewer
1. Are there better approaches?
2. What edge cases should I consider?
3. Any risks with this approach?
4. Performance implications?
```

### 3. Submit for review
Call `get_external_review(plan=<document>, context=<additional context>)`

### 4. Process the response
The external model will return:
- **Assessment**: overall viability rating
- **Issues**: potential problems found
- **Alternatives**: other approaches to consider
- **Recommendations**: specific suggestions

### 5. Present to user
Show the external review as a structured summary:
- Highlight any CRITICAL issues that should block implementation
- List alternatives worth considering
- Note any edge cases to add to tests
- If `require_approval_on_issues` is enabled and issues were found, ask user before proceeding

### 6. After implementation
When the feature/fix is complete, call `request_audit()` with:
- Task ID
- Files changed
- Test results

This provides independent verification that the implementation matches the plan.

## Configuration

Requires:
- OpenRouter API key configured (`/ec:configure` or `OPENROUTER_API_KEY` env var)
- External validation enabled (`/ec:ensemble on`)

Model can be changed via `/ec:ensemble model <model-id>` or `/ec:configure`.
