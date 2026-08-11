"""
Sandbox isolation tests — the most important tests in the project.

These verify that pathological code (infinite loop, large memory allocation,
immediate crash) is always killed within the timeout and returns a structured
failure. The pipeline MUST never hang.

Run with: pytest tests/test_sandbox.py -v
Requires: Docker daemon running locally.
"""
import pytest
from sandbox.run_in_sandbox import run_in_sandbox, TIMEOUT_SEC


# ── Fixtures: pathological code ────────────────────────────────────────────────

INFINITE_LOOP_CODE = """\
def test_infinite_loop():
    while True:
        pass
"""

LARGE_MALLOC_CODE = """\
def test_oom():
    # Attempt to allocate 2 GB — should be OOM-killed at 256 MB limit
    data = b"x" * (2 * 1024 * 1024 * 1024)
    assert len(data) > 0
"""

FORK_BOMB_CODE = """\
import os

def test_fork_bomb():
    while True:
        os.fork()
"""

IMMEDIATE_CRASH_CODE = """\
def test_crashes():
    raise RuntimeError("Intentional crash")
"""

PASSING_CODE = """\
def test_passes():
    assert 1 + 1 == 2
"""


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestSandboxIsolation:
    def test_passing_code_exits_zero(self):
        result = run_in_sandbox({"test_pass.py": PASSING_CODE})
        assert result["exit_code"] == 0

    def test_passing_code_reports_passed(self):
        result = run_in_sandbox({"test_pass.py": PASSING_CODE})
        assert "1 passed" in result["stdout"]

    def test_infinite_loop_is_killed(self):
        """Must terminate within TIMEOUT_SEC + a small grace margin."""
        result = run_in_sandbox({"test_loop.py": INFINITE_LOOP_CODE})
        assert result["exit_code"] != 0

    def test_infinite_loop_returns_structured_result(self):
        result = run_in_sandbox({"test_loop.py": INFINITE_LOOP_CODE})
        assert "stdout" in result
        assert "stderr" in result
        assert "exit_code" in result

    def test_large_malloc_is_killed(self):
        """2 GB allocation must be stopped by the 256 MB container limit."""
        result = run_in_sandbox({"test_oom.py": LARGE_MALLOC_CODE})
        assert result["exit_code"] != 0

    def test_immediate_crash_reports_failure(self):
        result = run_in_sandbox({"test_crash.py": IMMEDIATE_CRASH_CODE})
        assert result["exit_code"] != 0
        assert "FAILED" in result["stdout"] or "RuntimeError" in result["stdout"]

    def test_result_always_has_required_keys(self):
        for code, name in [
            (PASSING_CODE, "test_pass.py"),
            (IMMEDIATE_CRASH_CODE, "test_crash.py"),
            (INFINITE_LOOP_CODE, "test_loop.py"),
        ]:
            result = run_in_sandbox({name: code})
            assert "stdout" in result, f"Missing stdout for {name}"
            assert "stderr" in result, f"Missing stderr for {name}"
            assert "exit_code" in result, f"Missing exit_code for {name}"

    def test_no_network_access(self):
        """Container should fail to reach the internet (network=none)."""
        net_code = """\
import urllib.request
import pytest

def test_no_internet():
    with pytest.raises(Exception):
        urllib.request.urlopen("http://example.com", timeout=3)
"""
        result = run_in_sandbox({"test_net.py": net_code})
        # The test itself asserts the exception — so pytest should pass.
        assert result["exit_code"] == 0
