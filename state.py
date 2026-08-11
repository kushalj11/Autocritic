"""
Shared state schema — one JSON-serializable object passed between every agent
and appended to history after every iteration.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Literal, Optional


@dataclass
class Subtask:
    id: str
    description: str
    acceptance_criteria: List[str]


@dataclass
class BugReport:
    failed_criterion: str
    expected: str
    actual: str
    suspected_cause: str


@dataclass
class CodeChange:
    subtask_id: str
    file_path: str
    content: str
    diff: str = ""


@dataclass
class TestResult:
    passed: bool
    stdout: str
    stderr: str
    exit_code: int
    failed_tests: List[str] = field(default_factory=list)


@dataclass
class Verdict:
    approved: bool
    bug_report: Optional[BugReport] = None

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "bug_report": asdict(self.bug_report) if self.bug_report else None,
        }


@dataclass
class PipelineState:
    feature_request: str
    subtasks: List[Subtask] = field(default_factory=list)
    current_subtask_index: int = 0
    code_diff: str = ""
    test_results: Optional[TestResult] = None
    critic_verdict: Optional[Verdict] = None
    iteration_count: int = 0
    max_iterations: int = 5
    status: Literal["in_progress", "done", "stuck"] = "in_progress"
    history: List[dict] = field(default_factory=list)
    stuck_subtask_ids: List[str] = field(default_factory=list)

    # ── Serialization ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "feature_request": self.feature_request,
            "subtasks": [asdict(s) for s in self.subtasks],
            "current_subtask_index": self.current_subtask_index,
            "code_diff": self.code_diff,
            "test_results": asdict(self.test_results) if self.test_results else None,
            "critic_verdict": self.critic_verdict.to_dict() if self.critic_verdict else None,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "status": self.status,
            "history": self.history,
            "stuck_subtask_ids": self.stuck_subtask_ids,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineState":
        subtasks = [Subtask(**s) for s in data.get("subtasks", [])]
        test_results = TestResult(**data["test_results"]) if data.get("test_results") else None
        verdict: Optional[Verdict] = None
        if data.get("critic_verdict"):
            v = data["critic_verdict"]
            bug = BugReport(**v["bug_report"]) if v.get("bug_report") else None
            verdict = Verdict(approved=v["approved"], bug_report=bug)
        return cls(
            feature_request=data["feature_request"],
            subtasks=subtasks,
            current_subtask_index=data.get("current_subtask_index", 0),
            code_diff=data.get("code_diff", ""),
            test_results=test_results,
            critic_verdict=verdict,
            iteration_count=data.get("iteration_count", 0),
            max_iterations=data.get("max_iterations", 5),
            status=data.get("status", "in_progress"),
            history=data.get("history", []),
            stuck_subtask_ids=data.get("stuck_subtask_ids", []),
        )

    @classmethod
    def from_json(cls, raw: str) -> "PipelineState":
        return cls.from_dict(json.loads(raw))
