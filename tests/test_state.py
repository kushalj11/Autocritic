"""
Tests for state.py — verifies round-trip JSON serialization with no data loss.
"""
import json
import pytest
from state import (
    BugReport, CodeChange, PipelineState, Subtask, TestResult, Verdict
)


@pytest.fixture()
def full_state() -> PipelineState:
    bug = BugReport(
        failed_criterion="returns 401 when token is absent",
        expected="HTTP 401",
        actual="HTTP 200",
        suspected_cause="Auth middleware not applied to this route",
    )
    verdict = Verdict(approved=False, bug_report=bug)
    tr = TestResult(
        passed=False,
        stdout="FAILED test_auth.py::test_no_token",
        stderr="",
        exit_code=1,
        failed_tests=["test_auth.py::test_no_token"],
    )
    state = PipelineState(
        feature_request="Add JWT authentication to /api/data endpoint",
        max_iterations=3,
    )
    state.subtasks = [
        Subtask(
            id="subtask_1",
            description="Implement JWT validation middleware",
            acceptance_criteria=[
                "returns 401 when token is absent",
                "returns 401 when token is expired",
                "returns 200 with valid token",
            ],
        )
    ]
    state.test_results = tr
    state.critic_verdict = verdict
    state.history.append({"subtask_id": "subtask_1", "iteration": 0, "approved": False})
    return state


class TestPipelineStateRoundTrip:
    def test_to_json_is_valid_json(self, full_state):
        raw = full_state.to_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_round_trip_feature_request(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert restored.feature_request == full_state.feature_request

    def test_round_trip_max_iterations(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert restored.max_iterations == 3

    def test_round_trip_subtasks(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert len(restored.subtasks) == 1
        assert restored.subtasks[0].id == "subtask_1"
        assert len(restored.subtasks[0].acceptance_criteria) == 3

    def test_round_trip_test_results(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert restored.test_results is not None
        assert restored.test_results.passed is False
        assert restored.test_results.exit_code == 1
        assert restored.test_results.failed_tests == ["test_auth.py::test_no_token"]

    def test_round_trip_critic_verdict(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert restored.critic_verdict is not None
        assert restored.critic_verdict.approved is False
        assert restored.critic_verdict.bug_report is not None
        assert restored.critic_verdict.bug_report.failed_criterion == (
            "returns 401 when token is absent"
        )

    def test_round_trip_history(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert len(restored.history) == 1
        assert restored.history[0]["subtask_id"] == "subtask_1"

    def test_round_trip_status_default(self, full_state):
        restored = PipelineState.from_json(full_state.to_json())
        assert restored.status == "in_progress"

    def test_round_trip_no_data_loss(self, full_state):
        """Two round trips must produce identical JSON."""
        first = full_state.to_json()
        second = PipelineState.from_json(first).to_json()
        assert json.loads(first) == json.loads(second)


class TestVerdictWithoutBugReport:
    def test_approved_verdict_serializes(self):
        v = Verdict(approved=True, bug_report=None)
        d = v.to_dict()
        assert d["approved"] is True
        assert d["bug_report"] is None

    def test_state_with_approved_verdict_roundtrips(self):
        state = PipelineState(feature_request="test")
        state.critic_verdict = Verdict(approved=True)
        restored = PipelineState.from_json(state.to_json())
        assert restored.critic_verdict is not None
        assert restored.critic_verdict.approved is True
        assert restored.critic_verdict.bug_report is None
