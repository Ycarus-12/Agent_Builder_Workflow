"""Deterministic assertions for functional-QA (functional-qa-evals §, 1-9).

Verdict vs the ground-truth oracle, mode/status coupling by build_type, fail and
validate-on-apply coupling, AC coverage, the no-security/no-acceptance content
check, and the independence (no-manifest-citation) content check.
"""

from __future__ import annotations

import json
import re

from .assertions import CaseResult, _is_pure_json

_BANNED_SECURITY = (
    "security review passed", "no vulnerabilities", "secure", "approved for production",
    "accepted", "sign-off", "cleared for release",
)
_BANNED_MANIFEST = (
    "per the build facts", "the manifest says", "the criteria map confirms",
    "build reported", "as the build claims", "according to the manifest",
)
_EXECUTED = {"code", "agent_creation"}


def _contains_any(text: str, needles) -> str | None:
    low = text.lower()
    for n in needles:
        if n in low:
            return n
    return None


def check_qa(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}
    oracle = fixture.oracle or {}
    inputs = list(fixture.acceptance_criteria)

    try:
        v = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(v), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    bt = v["build_type"]
    status = v["qa_status"]
    mode = v["verification_mode"]
    verdicts = v["criteria_verdicts"]

    # 6. AC coverage (order + exact set)
    mapped = [cv["criterion"] for cv in verdicts]
    if mapped != inputs:
        f.append(f"criteria_verdicts {mapped} != input criteria (in order) {inputs}")

    # 1. Verdict matches oracle
    if "qa_status" in oracle and status != oracle["qa_status"]:
        f.append(f"qa_status {status!r} != oracle {oracle['qa_status']!r}")
    oracle_verdicts = oracle.get("verdicts", [])
    if oracle_verdicts and len(oracle_verdicts) == len(verdicts):
        for i, (cv, exp) in enumerate(zip(verdicts, oracle_verdicts)):
            if cv["verdict"] != exp:
                f.append(f"criteria_verdicts[{i}] {cv['verdict']!r} != oracle {exp!r}")

    # 2. Mode coupling
    expected_mode = (
        "executed" if bt in _EXECUTED else "staging" if bt == "config_applied" else "reasoning_review"
    )
    if mode != expected_mode:
        f.append(f"verification_mode {mode!r} != expected {expected_mode!r} for {bt}")

    # 3. Status-by-mode coupling
    if bt in _EXECUTED or bt == "config_applied":
        if status not in ("pass", "fail"):
            f.append(f"{bt}: qa_status must be pass|fail, got {status!r}")
        if any(cv["verdict"] not in ("pass", "fail") for cv in verdicts):
            f.append(f"{bt}: every criterion verdict must be pass|fail")
        if v["validate_on_apply"] != []:
            f.append(f"{bt}: validate_on_apply must be []")
    elif bt == "config_instructions":
        if status == "pass":
            f.append("config_instructions: qa_status 'pass' is never valid")
        if status == "pass_pending_apply":
            if any(cv["verdict"] != "unverifiable_pending_apply" for cv in verdicts):
                f.append("pass_pending_apply: all verdicts must be unverifiable_pending_apply")
            if len(v["validate_on_apply"]) != len(inputs):
                f.append("pass_pending_apply: validate_on_apply needs one entry per criterion")
        elif status == "fail" and not any(cv["verdict"] == "fail" for cv in verdicts):
            f.append("config_instructions fail: at least one criterion verdict must be fail")

    # 4. Fail coupling
    fr = v["failure_report"]
    fail_set = {cv["criterion"] for cv in verdicts if cv["verdict"] == "fail"}
    if (fr is not None) != (status == "fail"):
        f.append("failure_report must be non-null iff qa_status == fail")
    if fr is not None:
        if not fr["failed_criteria"]:
            f.append("failure_report.failed_criteria must be non-empty when fail")
        if set(fr["failed_criteria"]) != fail_set:
            f.append(f"failed_criteria {sorted(fr['failed_criteria'])} != failing verdicts {sorted(fail_set)}")

    # 5. validate_on_apply coupling
    voa_expected = bt == "config_instructions" and status == "pass_pending_apply"
    if (len(v["validate_on_apply"]) > 0) != voa_expected:
        f.append("validate_on_apply non-empty iff config_instructions + pass_pending_apply")

    # 7. No security claim / no acceptance
    sec_blob = " | ".join(
        [v["independence_note"]]
        + [cv["evidence"] for cv in verdicts]
        + [fi["summary"] + " " + fi["detail"] for fi in v["findings"]]
    )
    hit = _contains_any(sec_blob, _BANNED_SECURITY)
    if hit:
        f.append(f"banned security/acceptance language: '{hit}'")

    # 8. Independence: no evidence cites the manifest as proof
    for cv in verdicts:
        h = _contains_any(cv["evidence"], _BANNED_MANIFEST)
        if h:
            f.append(f"evidence cites the manifest as proof: '{h}'")
            break

    return CaseResult(fixture.case_id, passed=not f, failures=f)
