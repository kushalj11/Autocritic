"""
Test-runner agent — thin wrapper that converts raw sandbox output into a
structured TestResult.

Downstream agents (critic, orchestrator) NEVER parse raw stdout/stderr
themselves — they only consume TestResult fields.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import CodeChange, TestResult
from sandbox.run_in_sandbox import run_in_sandbox


def _parse_failed_tests(output: str) -> list[str]:
    """Extract test IDs from pytest -v output lines ending with FAILED."""
    failed = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.endswith(" FAILED") or " FAILED " in stripped:
            parts = stripped.split()
            if parts:
                failed.append(parts[0])
    return failed


def run_tests(code_change: CodeChange) -> TestResult:
    """
    Copy code_change files into the sandbox and run pytest.

    Expects code_change to carry .test_file_path and .test_content
    (set by the Coder agent).  Falls back gracefully if absent.
    """
    files: dict[str, str] = {code_change.file_path: code_change.content}

    test_file_path = getattr(code_change, "test_file_path", None)
    test_content = getattr(code_change, "test_content", None)
    if test_file_path and test_content:
        files[test_file_path] = test_content

    result = run_in_sandbox(files)
    stdout: str = result["stdout"]
    stderr: str = result["stderr"]
    exit_code: int = result["exit_code"]
    passed = exit_code == 0
    failed_tests = _parse_failed_tests(stdout)

    return TestResult(
        passed=passed,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        failed_tests=failed_tests,
    )
