"""
Orchestrator — wires Planner → Coder → TestRunner → Critic with the
self-correction loop and explicit stuck-detection.

Loop invariant: the while loop ALWAYS terminates because iteration is bounded
by max_iterations and no exception can bypass the increment (try/except wraps
every agent call).
"""
from __future__ import annotations

import json
import os
import sys
import difflib
from dataclasses import asdict
from datetime import datetime

from state import PipelineState, Verdict
from agents.planner import plan
from agents.coder import implement
from agents.test_runner import run_tests
from agents.critic import review
from agents.summarizer import summarize

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _diff(old: str, new: str, filename: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def _save_log(state: PipelineState, run_id: str) -> None:
    path = os.path.join(LOG_DIR, f"run_{run_id}.json")
    with open(path, "w") as fh:
        json.dump(state.to_dict(), fh, indent=2)


def _write_output(run_id: str, file_path: str, content: str, test_file_path: str, test_content: str) -> None:
    """Write approved implementation + test file to output/<run_id>/ so the user can read them."""
    run_out = os.path.join(OUTPUT_DIR, run_id)
    os.makedirs(run_out, exist_ok=True)
    for path, text in [(file_path, content), (test_file_path, test_content)]:
        dest = os.path.join(run_out, os.path.basename(path))
        with open(dest, "w") as fh:
            fh.write(text)


def _print(msg: str) -> None:
    print(msg, flush=True)


# ── Main loop ──────────────────────────────────────────────────────────────────

def run(feature_request: str, max_iterations: int = 5) -> PipelineState:
    """
    Execute the full pipeline for *feature_request*.

    Returns the final PipelineState (status = "done" | "stuck").
    Stuck subtasks are logged with status "stuck" and never silently dropped.
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    state = PipelineState(
        feature_request=feature_request,
        max_iterations=max_iterations,
    )

    _print(f"\n{'='*62}")
    _print("  AUTOCRITIC — Self-Correcting Code Review Pipeline")
    _print(f"{'='*62}")
    _print(f"  Feature: {feature_request}\n")

    # ── Step 1: Plan ──────────────────────────────────────────────
    _print("[PLANNER] Generating subtasks…")
    try:
        state.subtasks = plan(feature_request)
    except Exception as exc:
        _print(f"  ERROR: Planner failed — {exc}")
        state.status = "stuck"
        _save_log(state, run_id)
        return state

    _print(f"  → {len(state.subtasks)} subtask(s) planned")
    for s in state.subtasks:
        _print(f"     • [{s.id}] {s.description}")
    _print("")

    # Accumulated file context shared across subtasks
    context: dict[str, str] = {}
    any_approved = False

    # ── Step 2: Subtask loop ──────────────────────────────────────
    for idx, subtask in enumerate(state.subtasks):
        state.current_subtask_index = idx
        _print(f"[SUBTASK {idx+1}/{len(state.subtasks)}] {subtask.description}")
        _print(f"  Criteria: {len(subtask.acceptance_criteria)}")

        bug_report = None
        verdict = Verdict(approved=False)
        iteration = 0

        while iteration < max_iterations:
            state.iteration_count = iteration

            # ── Coder ──────────────────────────────────────────
            _print(f"  [iter {iteration+1}] Coder implementing…")
            try:
                code_change = implement(subtask, context, bug_report)
            except Exception as exc:
                _print(f"  [iter {iteration+1}] Coder ERROR: {exc}")
                iteration += 1
                continue

            old = context.get(code_change.file_path, "")
            code_change.diff = _diff(old, code_change.content, code_change.file_path)

            # ── Test runner ────────────────────────────────────
            _print(f"  [iter {iteration+1}] Running tests in sandbox…")
            try:
                test_result = run_tests(code_change)
            except Exception as exc:
                _print(f"  [iter {iteration+1}] TestRunner ERROR: {exc}")
                iteration += 1
                continue

            state.test_results = test_result
            state.code_diff = code_change.diff

            # ── Critic ─────────────────────────────────────────
            _print(f"  [iter {iteration+1}] Critic reviewing…")
            try:
                verdict = review(subtask, test_result, code_change.diff)
            except Exception as exc:
                _print(f"  [iter {iteration+1}] Critic ERROR: {exc}")
                iteration += 1
                continue

            state.critic_verdict = verdict

            # Record this iteration in the history trace
            state.history.append({
                "subtask_id": subtask.id,
                "iteration": iteration,
                "file_path": code_change.file_path,
                "diff": code_change.diff,
                "test_passed": test_result.passed,
                "test_stdout": test_result.stdout,
                "test_stderr": test_result.stderr,
                "test_exit_code": test_result.exit_code,
                "failed_tests": test_result.failed_tests,
                "approved": verdict.approved,
                "bug_report": asdict(verdict.bug_report) if verdict.bug_report else None,
            })
            _save_log(state, run_id)

            if verdict.approved:
                _print(f"  [iter {iteration+1}] ✓ APPROVED")
                context[code_change.file_path] = code_change.content
                any_approved = True
                _write_output(
                    run_id,
                    code_change.file_path,
                    code_change.content,
                    getattr(code_change, "test_file_path", "test_output.py"),
                    getattr(code_change, "test_content", ""),
                )
                break

            bug_report = verdict.bug_report
            failed_what = bug_report.failed_criterion if bug_report else "unknown criterion"
            _print(f"  [iter {iteration+1}] ✗ Rejected — failed: {failed_what}")
            iteration += 1

        # ── Stuck detection ────────────────────────────────────
        if not verdict.approved:
            _print(f"  → STUCK after {max_iterations} iteration(s). Logging and continuing.")
            state.stuck_subtask_ids.append(subtask.id)
            state.history.append({
                "subtask_id": subtask.id,
                "status": "stuck",
                "iterations_exhausted": max_iterations,
                "last_bug_report": asdict(verdict.bug_report) if verdict.bug_report else None,
            })
            _save_log(state, run_id)
        else:
            _print("")

    # ── Final status ───────────────────────────────────────────────
    if state.stuck_subtask_ids and not any_approved:
        state.status = "stuck"
    elif state.stuck_subtask_ids:
        state.status = "stuck"   # partial success still counts as stuck
    else:
        state.status = "done"

    _save_log(state, run_id)

    # ── Summarizer (only on full success) ─────────────────────────
    readme_path = ""
    if state.status == "done" and context:
        _print("[SUMMARIZER] Writing README for generated code…")
        try:
            run_out = os.path.join(OUTPUT_DIR, run_id)
            readme_path = summarize(
                feature_request=feature_request,
                output_dir=run_out,
                approved_files=context,
            )
            _print(f"  → README written: output/{run_id}/README.md")
        except Exception as exc:
            _print(f"  WARNING: Summarizer failed — {exc}")

    _print(f"\n{'='*62}")
    _print(f"  Pipeline complete — status: {state.status.upper()}")
    if state.stuck_subtask_ids:
        _print(f"  Stuck subtasks  : {', '.join(state.stuck_subtask_ids)}")
    _print(f"  Trace saved to  : logs/run_{run_id}.json")
    _print(f"  Code written to : output/{run_id}/")
    if readme_path:
        _print(f"  README written  : output/{run_id}/README.md")
    _print(f"{'='*62}\n")
    return state


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orchestrator.py \"<feature request>\" [max_iterations]")
        print("Example: python orchestrator.py \"Add a function that checks if a number is prime.\"")
        sys.exit(1)

    feature = sys.argv[1]
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    final = run(feature, max_iterations=iters)
    sys.exit(0 if final.status == "done" else 1)
