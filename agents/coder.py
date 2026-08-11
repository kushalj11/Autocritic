"""
Coder agent — implements exactly one subtask at a time.

When a bug_report is supplied, the model MUST address the specific failed
criterion named in the report rather than rewriting everything.
Output is syntax-checked before being returned downstream.
"""
from __future__ import annotations

import ast
import json
import os
from google import genai
from dotenv import load_dotenv
from state import BugReport, CodeChange, Subtask

load_dotenv()
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODEL = "gemini-2.5-flash"

_SYSTEM = """\
You are a senior Python engineer implementing a single subtask. \
Output ONLY valid JSON — no prose, no markdown fences.

Output schema:
{
  "file_path": "relative/path/to/module.py",
  "content": "<complete file content as a string>",
  "test_file_path": "relative/path/to/test_module.py",
  "test_content": "<complete pytest test file content as a string>"
}

Rules:
- Implement the acceptance criteria exactly — nothing more, nothing less.
- If a bug_report is provided, fix ONLY the specific failed_criterion. \
  Do not change anything unrelated to the bug.
- Both files must be syntactically valid Python.
- Tests must import from the module you implement and use pytest assertions.
- Do not use unittest or any test framework other than pytest.
- Return ONLY the JSON object."""


def _check_syntax(code: str, label: str) -> None:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in {label}: {exc}") from exc


def implement(
    subtask: Subtask,
    context: dict[str, str],
    bug_report: BugReport | None = None,
) -> CodeChange:
    """
    Generate code + tests for a single subtask.

    Args:
        subtask:    The subtask to implement.
        context:    Dict of {file_path: content} for files already written.
        bug_report: If provided, the coder must fix the specific failed criterion.

    Returns:
        CodeChange with .file_path, .content, .test_file_path, .test_content.
    """
    parts = [
        f"Subtask ID  : {subtask.id}",
        f"Description : {subtask.description}",
        "",
        "Acceptance criteria (ALL must pass):",
        *[f"  [{i+1}] {c}" for i, c in enumerate(subtask.acceptance_criteria)],
    ]
    if context:
        parts += ["", "Existing files (read-only context):"]
        for path, content in context.items():
            parts += [f"\n# {path}", content]
    if bug_report:
        parts += [
            "",
            "⚠ Previous attempt FAILED. Fix this SPECIFIC issue — do not rewrite everything:",
            f"  Failed criterion : {bug_report.failed_criterion}",
            f"  Expected         : {bug_report.expected}",
            f"  Actual           : {bug_report.actual}",
            f"  Suspected cause  : {bug_report.suspected_cause}",
        ]

    response = _client.models.generate_content(
        model=MODEL,
        config={"system_instruction": _SYSTEM, "max_output_tokens": 4096},
        contents="\n".join(parts),
    )
    text = response.text
    raw = json.loads(_strip_fences(text))

    _check_syntax(raw["content"], raw["file_path"])
    _check_syntax(raw["test_content"], raw["test_file_path"])

    change = CodeChange(
        subtask_id=subtask.id,
        file_path=raw["file_path"],
        content=raw["content"],
    )
    # Attach test file as extra attributes for the test runner
    change.test_file_path = raw["test_file_path"]  # type: ignore[attr-defined]
    change.test_content = raw["test_content"]       # type: ignore[attr-defined]
    return change


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return text.strip()
