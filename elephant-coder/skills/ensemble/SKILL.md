---
name: ensemble
description: Enable/disable second opinion from an external model (OpenRouter) for features and bugs
---

Toggle ensemble mode for the current project. When enabled, Claude automatically asks
an external model on OpenRouter for a second opinion before implementing new features or bug fixes.

## Usage

- `/ec:ensemble` — show current status and toggle
- `/ec:ensemble on` — enable ensemble mode
- `/ec:ensemble off` — disable ensemble mode
- `/ec:ensemble model <model-id>` — change the external model

## How it works

When ensemble mode is **enabled**:
1. Before implementing a new feature or bug fix, Claude calls `get_external_review()` with:
   - The proposed plan/approach
   - Relevant context from elephant-coder memory
2. The external model reviews the plan and provides:
   - Potential issues or blind spots
   - Alternative approaches
   - Risk assessment
3. Claude considers the feedback before proceeding
4. After implementation, Claude calls `request_audit()` for independent verification

When ensemble mode is **disabled**:
- Claude works normally without external validation

## Steps

### Show status
1. Read settings from `.claude/elephant-coder.local.md`
2. Check `external_validation.enabled`
3. Show:
   - Status: enabled/disabled
   - Model: current model ID
   - API key: configured (masked) or missing
   - Plan validation: on/off
   - Audit completed tasks: on/off

### Toggle on
1. Check if `external_validation.openrouter_api_key` is set
2. If not, ask the user for their OpenRouter API key
3. Set `external_validation.enabled = true` via `update_settings()`
4. Confirm: "Ensemble mode enabled — using <model> for second opinions"

### Toggle off
1. Set `external_validation.enabled = false` via `update_settings()`
2. Confirm: "Ensemble mode disabled"

### Change model
1. Update `external_validation.model` via settings
2. Common models:
   - `google/gemini-3.1-flash-lite-preview` (fast, cheap)
   - `anthropic/claude-sonnet-4` (strong reasoning)
   - `openai/gpt-4o-mini` (balanced)
   - `meta-llama/llama-3.1-70b-instruct` (open source)
3. Confirm: "External model changed to <model>"

## Integration

The ensemble workflow hooks into elephant-coder's existing `get_external_review()` and
`request_audit()` MCP tools. The SessionStart hook checks if ensemble mode is enabled
and reminds Claude to use external validation for significant changes.
