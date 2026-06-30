"""Deterministic assertions for the two security agents (security-evals §A.3).

Shared: schema validity, sequential finding ids (from 001, correct prefix),
no verdict/pass/block field (the orchestrator derives the block, not the agent),
non-empty human_summary, pure JSON. Governance adds: applied_sensitivity matches
the input data_sensitivity (unspecified -> customer), governance_reference present.
"""

from __future__ import annotations

import json
import re

from ..sensitivity import DataSensitivity, effective_sensitivity
from .assertions import CaseResult, _is_pure_json

_VERDICT_KEYS = {"verdict", "pass", "block", "pass_block"}


def _has_verdict_key(obj) -> bool:
    if isinstance(obj, dict):
        if any(k.lower() in _VERDICT_KEYS for k in obj):
            return True
        return any(_has_verdict_key(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_verdict_key(v) for v in obj)
    return False


def _ids_sequential(findings, prefix: str) -> str | None:
    nums = []
    for fi in findings:
        m = re.match(rf"^{prefix}-(\d{{3}})$", fi.get("finding_id", ""))
        if not m:
            return f"finding_id {fi.get('finding_id')!r} does not match {prefix}-NNN"
        nums.append(int(m.group(1)))
    if nums != list(range(1, len(nums) + 1)):
        return f"finding ids not sequential from 001: {nums}"
    return None


def check_security(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}
    kind = fixture.kind  # "vuln" | "gov"
    prefix = "SEC-V" if kind == "vuln" else "SEC-G"

    try:
        out = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(out), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    findings = out["findings"]
    if a.get("finding_ids_sequential", True):
        err = _ids_sequential(findings, prefix)
        if err:
            f.append(err)

    if a.get("no_verdict_field", True) and _has_verdict_key(out):
        f.append("output contains a verdict/pass/block field (orchestrator derives this)")

    if kind == "gov" and a.get("applied_sensitivity_correct", True):
        raw = fixture.data_sensitivity or "unspecified"
        expected = effective_sensitivity(DataSensitivity(raw)).value
        if out.get("applied_sensitivity") != expected:
            f.append(
                f"applied_sensitivity {out.get('applied_sensitivity')!r} != expected {expected!r} "
                f"(from data_sensitivity {raw!r})"
            )

    return CaseResult(fixture.case_id, passed=not f, failures=f)
