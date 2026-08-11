# Autocritic — Self-Correcting Code Review Pipeline

A multi-agent system that takes a plain-English feature request, breaks it into
subtasks, writes code and tests for each one, runs those tests inside an
isolated Docker container, and has an AI critic check the results against
explicit acceptance criteria. If a subtask fails, the critic hands back a
targeted bug report and the coder tries again — up to `max_iterations` times —
until it passes or the pipeline gives up and marks it "stuck".

## How it works

1. **Planner** (`agents/planner.py`) turns the feature request into 2–5
   subtasks, each with a list of testable acceptance criteria.
2. **Coder** (`agents/coder.py`) writes an implementation + pytest file for
   the current subtask (and the bug report from the previous attempt, if any).
3. **Sandbox** (`sandbox/run_in_sandbox.py`) runs those tests inside a Docker
   container with no network access, memory/CPU limits, and a hard timeout.
4. **Critic** (`agents/critic.py`) reads the pytest output and decides whether
   every acceptance criterion is proven — no subjective code-quality opinions,
   just pass/fail against the criteria.
5. **Orchestrator** (`orchestrator.py`) wires these together in a loop, logs
   every iteration to `logs/`, and writes the final approved files to
   `output/<run_id>/`.

Each agent calls the Gemini API (`gemini-2.5-flash`) with a narrow,
single-purpose system prompt.

## Setup

```bash
git clone <repo>
cd autocritic

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)

docker info   # make sure the Docker daemon is running — the sandbox needs it
```

## Running

```bash
python orchestrator.py "Add a function that checks if a number is prime."

# with a custom iteration cap (default 5)
python orchestrator.py "Add rate limiting: max 5 requests per IP per minute." 8
```

Exit code is `0` if every subtask was approved, `1` if any subtask got stuck.

## Tests

```bash
# no API key needed
pytest tests/test_state.py tests/test_sandbox.py -v

# needs GEMINI_API_KEY and a running Docker daemon
pytest tests/ -v
```

## Project layout

```
state.py                  shared dataclasses passed between every agent
orchestrator.py            main loop: plan -> code -> test -> review -> repeat
agents/
  planner.py                feature request -> subtasks + acceptance criteria
  coder.py                   subtask -> implementation + tests
  test_runner.py             runs tests in the sandbox, parses results
  critic.py                  test results -> approve/reject + bug report
  summarizer.py               writes a README for the generated code on success
sandbox/
  Dockerfile                 python:3.11-slim + pytest
  run_in_sandbox.py          isolated, resource-limited container execution
tests/                      unit tests for state, sandbox, and planner
logs/                       one JSON trace per run (gitignored)
output/                     approved files per run (gitignored)
```

## Design notes

- **Sandbox isolation**: containers run with `--network none`, a 256 MB memory
  cap, 50% CPU quota, and a 30-second hard timeout enforced by
  `container.wait(timeout=...)`. Runaway code (infinite loops, fork bombs) is
  force-killed rather than hanging the pipeline.
- **Critic scope**: the critic only checks acceptance criteria against test
  evidence — it never comments on style or architecture, and never invents
  criteria the planner didn't specify.
- **Stuck detection**: if a subtask doesn't pass after `max_iterations`, it's
  recorded in `stuck_subtask_ids` and the pipeline moves on to the next
  subtask instead of looping forever or crashing.
