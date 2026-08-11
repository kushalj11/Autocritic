"""
Planner agent — turns a feature request into ordered subtasks, each with
explicit, testable acceptance criteria.

Every criterion must be phrased so a test can assert it:
  ✓ "raises ValueError when input is empty string"
  ✗ "handles bad input gracefully"
"""
from __future__ import annotations

import json
import os
from google import genai
from dotenv import load_dotenv
from state import Subtask

load_dotenv()
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODEL = "gemini-2.5-flash"

_SYSTEM = """\
You are a software planning agent. Break the feature request into 2–5 ordered, \
independent subtasks. Output ONLY a valid JSON array — no prose, no markdown fences.

Each acceptance criterion MUST be phrased as something a pytest assertion can verify, e.g.:
  "returns 401 when Authorization header is absent"
  "raises ValueError for empty string input"
  "function returns True for prime numbers and False for composites"

Never write vague criteria like "handles errors properly" or "works correctly".

Output schema (strict JSON array):
[
  {
    "id": "subtask_1",
    "description": "One clear sentence describing what to implement.",
    "acceptance_criteria": [
      "specific, assertable criterion",
      "another specific criterion"
    ]
  }
]"""


def plan(feature_request: str) -> list[Subtask]:
    """Return an ordered list of Subtasks for the given feature request."""
    response = _client.models.generate_content(
        model=MODEL,
        config={"system_instruction": _SYSTEM, "max_output_tokens": 2048},
        contents=f"Feature request:\n{feature_request}",
    )
    text = response.text
    text = _strip_fences(text)
    raw = json.loads(text)
    return [Subtask(**item) for item in raw]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return text.strip()
