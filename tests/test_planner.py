"""
Planner agent unit tests — validates output schema without running the full pipeline.
Requires ANTHROPIC_API_KEY to be set; skipped otherwise.
"""
import os
import pytest
from state import Subtask


def _requires_api():
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")


class TestPlannerOutput:
    def test_plan_returns_list_of_subtasks(self):
        _requires_api()
        from agents.planner import plan
        subtasks = plan("Add a function that checks if a number is prime.")
        assert isinstance(subtasks, list)
        assert len(subtasks) >= 1

    def test_each_subtask_has_required_fields(self):
        _requires_api()
        from agents.planner import plan
        subtasks = plan("Add a function that reverses a string without using built-in reverse.")
        for s in subtasks:
            assert isinstance(s, Subtask)
            assert s.id
            assert s.description
            assert isinstance(s.acceptance_criteria, list)
            assert len(s.acceptance_criteria) >= 1

    def test_criteria_are_concrete(self):
        _requires_api()
        from agents.planner import plan
        subtasks = plan("Add password validation: >=8 chars, 1 number, 1 special character.")
        vague_phrases = ["properly", "correctly", "appropriately", "handles well"]
        for s in subtasks:
            for criterion in s.acceptance_criteria:
                for vague in vague_phrases:
                    assert vague not in criterion.lower(), (
                        f"Vague criterion detected: '{criterion}'"
                    )
