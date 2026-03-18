import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_engine import build_review_prompt, build_audit_prompt, parse_review_response


def test_build_review_prompt():
    prompt = build_review_prompt(
        plan="Add batch upsert to memory store",
        objectives=["Performance improvement"],
        evidence=["SQLite supports transactions"],
    )
    assert "batch upsert" in prompt.lower()
    assert "Performance improvement" in prompt
    assert "adversarial" in prompt.lower() or "flaw" in prompt.lower()


def test_build_audit_prompt():
    prompt = build_audit_prompt(
        task_desc="Add batch upsert method",
        files_changed=["memory_store.py"],
        test_results="5 passed, 0 failed",
    )
    assert "batch upsert" in prompt.lower()
    assert "memory_store.py" in prompt
    assert "5 passed" in prompt


def test_parse_review_response_with_issues():
    response = """
I found several issues:

**Critical:** The batch upsert doesn't handle the case where the database is locked by another process.

**Major:** No retry logic for transient failures.

**Minor:** Variable name 'cur' could be more descriptive.
"""
    issues = parse_review_response(response)
    assert len(issues) >= 2
    assert any(i["severity"] == "critical" for i in issues)
    assert any(i["severity"] == "major" for i in issues)


def test_parse_review_response_no_issues():
    response = "The plan looks solid. No issues found. Approved."
    issues = parse_review_response(response)
    assert len(issues) == 0
