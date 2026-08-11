"""
Critic agent — approves or rejects a subtask by checking TestResult against
the Planner's original acceptance criteria.

The critic NEVER applies subjective judgement ("good code", "needs refactoring").
It only asks: does the test output prove each criterion is met?
If any criterion is unmet it returns a BugReport that names the specific
failing criterion verbatim so the Coder knows exactly what to fix.
"""
from __future__ import annotations

import json
import os
from google import genai
from dotenv import load_dotenv
from state import BugReport, Subtask, TestResult, Verdict

load_dotenv()
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODEL = "gemini-2.5-flash"

_SYSTEM = """\
You are a code-review critic. Your ONLY job is to verify acceptance criteria \
against test evidence. Output ONLY valid JSON — no prose, no markdown fences.

Rules:
1. approved = true IFF every acceptance criterion is satisfied by the test output.
2. If ANY criterion is unmet, approved = false and bug_report is required.
3. bug_report.failed_criterion must be copied VERBATIM from the criteria list.
4. Do NOT comment on code style, naming, complexity, or anything not in the criteria.
5. Do NOT invent criteria that were not listed.

Output schema:
{
  "approved": true | false,
  "bug_report": null | {
    "failed_criterion": "<verbatim text of the failing criterion>",
    "expected": "<what the criterion requires>",
    "actual": "<what the test output shows instead>",
    "suspected_cause": "<one concise hypothesis about the root cause>"
  }
}"""


def review(subtask: Subtask, test_results: TestResult, code_diff: str) -> Verdict:
    """
    Evaluate whether test_results satisfy all of subtask.acceptance_criteria.

    Returns an approved Verdict or a Verdict with a targeted BugReport.
    """
    user_parts = [
        "Acceptance criteria (ALL must pass):",
        *[f"  [{i+1}] {c}" for i, c in enumerate(subtask.acceptance_criteria)],
        "",
        f"Tests passed : {test_results.passed}",
        f"Exit code    : {test_results.exit_code}",
        "",
        "--- pytest stdout ---",
        test_results.stdout or "(empty)",
        "",
        "--- stderr ---",
        test_results.stderr or "(empty)",
        "",
        "Failed test IDs:",
        "\n".join(test_results.failed_tests) if test_results.failed_tests else "(none)",
        "",
        "--- Code diff ---",
        code_diff or "(full new file — no previous version)",
    ]

    response = _client.models.generate_content(
        model=MODEL,
        config={"system_instruction": _SYSTEM, "max_output_tokens": 1024},
        contents="\n".join(user_parts),
    )
    text = response.text
    raw = json.loads(_strip_fences(text))

    bug: BugReport | None = None
    if raw.get("bug_report"):
        bug = BugReport(**raw["bug_report"])
    return Verdict(approved=raw["approved"], bug_report=bug)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return text.strip()
