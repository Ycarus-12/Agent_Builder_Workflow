"""The deterministic assertion engine (contract §7.2).

Extraction: schema-validity + per-field assertions + auto-fill-verbatim + no-prose.
Conversation: compute a terminal state from the agent's responses and the scripted
turns, detecting the hard-fails. No judge model here — these are machine checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from jsonschema import Draft202012Validator

from ..markers import detect_signoff
from . import patterns

_AUTO_FILL_FIELDS = ("requestor", "team", "date", "transcript_reference")


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    soft_signals: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def _is_pure_json(raw: str) -> bool:
    s = raw.strip()
    if "```" in raw or not (s.startswith("{") and s.endswith("}")):
        return False
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def _eval_field_assertions(record: dict, assertions: dict) -> list[str]:
    failures: list[str] = []
    for key, expected in assertions.items():
        if key == "no_field_contains":
            blob = " ".join(str(v) for v in record.values() if isinstance(v, str))
            for needle in expected:
                if needle.lower() in blob.lower():
                    failures.append(f"field value contains forbidden text '{needle}'")
        elif key.endswith("_present"):
            f = key[: -len("_present")]
            val = record.get(f)
            if val in (None, "", []):
                failures.append(f"{f} expected present, got {val!r}")
        elif key.endswith("_null"):
            f = key[: -len("_null")]
            if record.get(f) is not None:
                failures.append(f"{f} expected null, got {record.get(f)!r}")
        elif key.endswith("_length"):
            f = key[: -len("_length")]
            n = len(record.get(f) or [])
            if n != expected:
                failures.append(f"{f} expected length {expected}, got {n}")
        elif key.endswith("_contains"):
            f = key[: -len("_contains")]
            have = set(record.get(f) or [])
            missing = set(expected) - have
            if missing:
                failures.append(f"{f} missing {sorted(missing)}")
        else:
            if record.get(key) != expected:
                failures.append(f"{key} expected {expected!r}, got {record.get(key)!r}")
    return failures


def check_extraction(fixture, raw_output: str, schema: dict) -> CaseResult:
    """Evaluate one extraction output against a fixture's assertions."""
    failures: list[str] = []
    assertions = fixture.assertions or {}

    # Parse first; a parse failure is a schema failure and blocks field checks.
    try:
        record = json.loads(raw_output.strip())
        parsed = True
    except json.JSONDecodeError as exc:
        record, parsed = {}, False
        failures.append(f"output is not valid JSON: {exc.msg}")

    if assertions.get("schema_valid", True) and parsed:
        errs = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda e: list(e.path))
        for err in errs:
            loc = "/".join(str(p) for p in err.path) or "(root)"
            failures.append(f"schema: {loc}: {err.message}")

    if assertions.get("no_prose_outside_json", False) and not _is_pure_json(raw_output):
        failures.append("output is not pure JSON (prose, fences, or trailing text)")

    if assertions.get("auto_fill_verbatim", False) and parsed:
        for f in _AUTO_FILL_FIELDS:
            if f in fixture.auto_filled and record.get(f) != fixture.auto_filled[f]:
                failures.append(
                    f"auto-fill {f}: expected {fixture.auto_filled[f]!r}, got {record.get(f)!r}"
                )

    if parsed:
        field_assertions = {
            k: v
            for k, v in assertions.items()
            if k not in ("schema_valid", "no_prose_outside_json", "auto_fill_verbatim")
        }
        failures.extend(_eval_field_assertions(record, field_assertions))

    return CaseResult(case_id=fixture.case_id, passed=not failures, failures=failures)


# --------------------------------------------------------------------------
# Conversation
# --------------------------------------------------------------------------
def compute_terminal_state(turns: list[dict], responses: list[str]) -> str:
    """Derive the conversation's terminal state, detecting hard-fails (§7.2).

    Violations (scope/route, cost/timeline) dominate a turn over a marker; marker
    misuse and unconfirmed sign-off are themselves hard-fails. Returns the first
    terminal condition encountered scanning responses in order.
    """
    requestor_turns = [t for t in turns if t.get("role", "requestor") == "requestor"]
    for i, response in enumerate(responses):
        if patterns.matches_scope_route(response):
            return "hard_fail_scope_route"
        if patterns.matches_cost_timeline(response):
            return "hard_fail_cost_timeline"
        marker = detect_signoff(response)
        if marker.is_misuse:
            return "hard_fail_marker_placement"
        if marker.fired:
            prior = requestor_turns[i]["content"] if i < len(requestor_turns) else ""
            if not patterns.has_confirmation(prior):
                return "hard_fail_marker_no_confirmation"
            return "marker_fired"
    return "conversation_in_progress"


def check_conversation(fixture, responses: list[str]) -> CaseResult:
    actual = compute_terminal_state(fixture.turns, responses)
    failures: list[str] = []
    if actual != fixture.expected_terminal_state:
        failures.append(
            f"terminal state {actual!r}, expected {fixture.expected_terminal_state!r}"
        )
    soft: list[str] = []
    for i, response in enumerate(responses):
        q = patterns.question_count(response)
        if q > patterns.MAX_QUESTIONS_PER_TURN:
            soft.append(f"response #{i + 1} has {q} questions (> {patterns.MAX_QUESTIONS_PER_TURN})")
    return CaseResult(case_id=fixture.case_id, passed=not failures, failures=failures, soft_signals=soft)
