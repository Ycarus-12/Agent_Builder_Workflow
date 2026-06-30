"""Deterministic cross-field assertions for the build agent (build-evals §, 1-8).

Needs-input coupling, artifact-by-avenue coupling, verification-status coupling,
no-build-facts-without-execution, AC coverage, no-self-grade (banned verdict
phrases), sensitivity handling, and pure JSON.
"""

from __future__ import annotations

import json
import re

from .assertions import CaseResult, _is_pure_json

# Self-grade verdict language the build agent must never emit (it reports facts,
# QA grades). Audited list from build-evals assertion 6.
_SELF_GRADE = (
    "passes", "meets the criterion", "meets the acceptance", "satisfies the criterion",
    "works correctly", "fully functional", "verified working", "tested and correct",
    "acceptance criteria met",
)
_SECURITY_CLAIM = re.compile(r"security review (?:was )?(?:performed|passed|complete|completed|done)", re.IGNORECASE)
_SENSITIVE = {"customer", "financial", "regulated", "unspecified"}
_DATA_WORDS = ("data", "sensitiv", "pii", "redact", "encrypt", "access")


def _nn(v) -> bool:
    return v is not None


def check_build(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}

    try:
        m = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(m), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    status = m["build_status"]
    bt = m["build_type"]
    questions = m["questions"]
    artifact = m["artifact"]
    acmap = m["acceptance_criteria_map"]
    build_facts = m["build_facts"]
    needs_input = status == "needs_input"

    # 1. Needs-input coupling
    if (len(questions) > 0) != needs_input:
        f.append("questions non-empty must couple with build_status == needs_input")
    if needs_input:
        if artifact is not None:
            f.append("needs_input: artifact must be null")
        if m["qa_entrypoint"] is not None:
            f.append("needs_input: qa_entrypoint must be null")
        if build_facts != []:
            f.append("needs_input: build_facts must be []")
        if acmap != []:
            f.append("needs_input: acceptance_criteria_map must be []")
        ids = [q["id"] for q in questions]
        if len(ids) != len(set(ids)):
            f.append("needs_input: question ids must be unique")
    else:
        if questions != []:
            f.append("complete: questions must be []")

    # 2. Artifact-by-avenue coupling (complete only)
    if not needs_input:
        art = artifact or {}
        repo, commit = art.get("repo_path"), art.get("commit_hash")
        staging, guide = art.get("staging_ref"), art.get("config_guide")
        if bt in ("code", "agent_creation"):
            if not (_nn(repo) and _nn(commit) and not _nn(staging) and not _nn(guide)):
                f.append(f"{bt}: expect repo_path+commit_hash non-null, staging_ref+config_guide null")
        elif bt == "config_applied":
            if not (_nn(staging) and not _nn(repo) and not _nn(commit) and not _nn(guide)):
                f.append("config_applied: expect staging_ref non-null, others null")
        elif bt == "config_instructions":
            if not (_nn(guide) and not _nn(repo) and not _nn(commit) and not _nn(staging)):
                f.append("config_instructions: expect config_guide non-null, others null")

    # 3. Verification-status coupling
    expect_unverified = bt == "config_instructions"
    if (m["verification_status"] == "unverified_validate_on_apply") != expect_unverified:
        f.append("verification_status must be unverified_validate_on_apply iff config_instructions")

    # 4. No build facts without execution
    if (bt == "config_instructions" or needs_input) and build_facts != []:
        f.append("build_facts must be [] for config_instructions or needs_input")

    # 5. AC coverage (complete only)
    if not needs_input and a.get("ac_coverage", True):
        inputs = list(fixture.acceptance_criteria)
        mapped = [e["criterion"] for e in acmap]
        if sorted(mapped) != sorted(inputs):
            f.append(f"acceptance_criteria_map {mapped} != input criteria {inputs}")

    # 6. No self-grade
    blob = " ".join(e["addressed_by"] for e in acmap) + " " + " ".join(build_facts)
    low = blob.lower()
    for phrase in _SELF_GRADE:
        if phrase in low:
            f.append(f"self-grade language in build output: '{phrase}'")
            break

    # 7. Sensitivity handling
    sens = (fixture.spec_context or {}).get("data_sensitivity")
    if sens in _SENSITIVE:
        if not any(any(w in s.lower() for w in _DATA_WORDS) for s in m["assumptions"]):
            f.append(f"sensitivity {sens}: no assumptions entry addresses data handling")
    for s in m["assumptions"] + build_facts:
        if _SECURITY_CLAIM.search(s):
            f.append("build output claims the security review was performed")
            break

    return CaseResult(fixture.case_id, passed=not f, failures=f)
