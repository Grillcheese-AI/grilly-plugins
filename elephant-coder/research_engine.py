"""External model validation via OpenRouter API."""
from __future__ import annotations

import re
from typing import Any

DEFAULT_MODEL = "google/gemini-3.1-flash-lite-preview"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SEVERITY_PATTERN = re.compile(
    r"\*{0,2}(critical|major|minor)\*{0,2}[:\s]+(.+?)(?=\n\n|\*{0,2}(?:critical|major|minor)|$)",
    re.IGNORECASE | re.DOTALL,
)


def build_review_prompt(plan: str, objectives: list[str], evidence: list[str]) -> str:
    """Construct an adversarial review prompt for plan validation."""
    obj_block = "\n".join(f"  - {o}" for o in objectives)
    ev_block = "\n".join(f"  - {e}" for e in evidence)
    return (
        "You are an adversarial reviewer. Your job is to find every flaw, gap, and risk in the "
        "following plan. Be critical and thorough.\n\n"
        f"## Plan\n{plan}\n\n"
        f"## Objectives\n{obj_block}\n\n"
        f"## Evidence / Assumptions\n{ev_block}\n\n"
        "List all issues you find. For each issue, prefix with its severity: "
        "**Critical**, **Major**, or **Minor**. "
        "If the plan is sound, say 'No issues found.'"
    )


def build_audit_prompt(task_desc: str, files_changed: list[str], test_results: str) -> str:
    """Construct an audit prompt for completed task verification."""
    files_block = "\n".join(f"  - {f}" for f in files_changed)
    return (
        "You are a code auditor. Review the completed task below and verify correctness, "
        "completeness, and quality.\n\n"
        f"## Task Description\n{task_desc}\n\n"
        f"## Files Changed\n{files_block}\n\n"
        f"## Test Results\n{test_results}\n\n"
        "List any issues found. For each, prefix with **Critical**, **Major**, or **Minor**. "
        "If everything looks good, say 'No issues found.'"
    )


def call_openrouter(
    prompt: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """POST prompt to OpenRouter and return structured response.

    Returns:
        dict with keys: model, review (str), raw_response (dict)
    """
    import httpx  # local import — optional dependency

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60.0)
    response.raise_for_status()
    raw = response.json()

    review_text: str = ""
    try:
        review_text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        review_text = str(raw)

    return {
        "model": raw.get("model", model),
        "review": review_text,
        "raw_response": raw,
    }


def parse_review_response(text: str) -> list[dict[str, str]]:
    """Extract structured issues from a review response.

    Returns list of dicts with keys: severity, description.
    Returns empty list if no severity-tagged issues found.
    """
    issues: list[dict[str, str]] = []
    for match in _SEVERITY_PATTERN.finditer(text):
        severity = match.group(1).lower()
        description = match.group(2).strip()
        if description:
            issues.append({"severity": severity, "description": description})
    return issues
