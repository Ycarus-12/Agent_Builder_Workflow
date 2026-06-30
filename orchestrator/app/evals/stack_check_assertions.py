"""Deterministic assertions for stack-check (stack-check-evals §A, §B).

Given a fixture (intake_record + registry_mock.response + assertions) and the
agent's finding, checks: no invented matches, all mock matches present, sensitivity
floor, no_existing_coverage, registry_confidence, no recommendation language, and
pure JSON. expected_query_contains is live-only (the query isn't in the finding).
"""

from __future__ import annotations

import json
import re

from ..sensitivity import DataSensitivity, effective_sensitivity
from .assertions import CaseResult, _is_pure_json

# Floor/clearance ladder for the two-condition coverage rule.
_SENS_RANK = {"none": 0, "internal": 1, "customer": 2, "financial": 3, "regulated": 4}

_RECOMMENDATION_PATTERNS = (
    r"\brecommend", r"\bshould (?:configure|build|buy|use)", r"\bsuggest", r"\bwe could build",
    r"\bbest option", r"\bgo with\b", r"\bought to\b",
)


def _has_recommendation_language(text: str) -> str | None:
    low = text.lower()
    for pat in _RECOMMENDATION_PATTERNS:
        if re.search(pat, low):
            return pat
    return None


def _effective_floor(intake: dict) -> str:
    raw = intake.get("data_sensitivity", "unspecified") or "unspecified"
    return effective_sensitivity(DataSensitivity(raw)).value


def check_stack_check(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    failures: list[str] = []
    a = fixture.assertions or {}
    mock = (fixture.registry_mock or {}).get("response", [])

    try:
        finding = json.loads(raw_output.strip())
        parsed = True
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    if a.get("schema_valid", True):
        for err in sorted(Draft202012Validator(schema).iter_errors(finding), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            failures.append(f"schema: {loc}: {err.message}")

    if a.get("no_prose_outside_json", False) and not _is_pure_json(raw_output):
        failures.append("output is not pure JSON")

    matches = finding.get("matches", []) if parsed else []
    mock_cap_ids = {m["capability_id"] for m in mock}
    out_cap_ids = {m.get("capability_id") for m in matches}

    # 1. No invented matches; 2. all mock matches present.
    invented = out_cap_ids - mock_cap_ids
    if invented:
        failures.append(f"invented matches not in registry_mock: {sorted(invented)}")
    if a.get("all_mock_matches_present", True):
        missing = mock_cap_ids - out_cap_ids
        if missing:
            failures.append(f"mock matches dropped from output: {sorted(missing)}")

    # 3. Sensitivity floor consistency (fixture vs intake mapping).
    if "sensitivity_floor_applied" in a:
        expected_floor = _effective_floor(fixture.intake_record)
        if a["sensitivity_floor_applied"] != expected_floor:
            failures.append(
                f"sensitivity_floor_applied {a['sensitivity_floor_applied']!r} != "
                f"effective floor {expected_floor!r}"
            )

    # 4. no_existing_coverage.
    if "no_existing_coverage" in a and finding.get("no_existing_coverage") != a["no_existing_coverage"]:
        failures.append(
            f"no_existing_coverage {finding.get('no_existing_coverage')!r} != {a['no_existing_coverage']!r}"
        )

    # 5. registry_confidence.
    if "registry_confidence" in a and finding.get("registry_confidence") != a["registry_confidence"]:
        failures.append(
            f"registry_confidence {finding.get('registry_confidence')!r} != {a['registry_confidence']!r}"
        )

    if "matches_length" in a and len(matches) != a["matches_length"]:
        failures.append(f"matches length {len(matches)} != {a['matches_length']}")
    if "matches_0_support" in a:
        got = matches[0].get("support") if matches else None
        if got != a["matches_0_support"]:
            failures.append(f"matches[0].support {got!r} != {a['matches_0_support']!r}")
    if "systems_searched_contains" in a:
        have = set(finding.get("systems_searched", []))
        missing = set(a["systems_searched_contains"]) - have
        if missing:
            failures.append(f"systems_searched missing {sorted(missing)}")

    # 6. No recommendation language in finding_summary / relevance_notes.
    if a.get("no_recommendation_language", True):
        blob = finding.get("finding_summary", "") + " " + " ".join(
            m.get("relevance_note", "") for m in matches
        )
        hit = _has_recommendation_language(blob)
        if hit:
            failures.append(f"recommendation language in finding: matched /{hit}/")

    return CaseResult(fixture.case_id, passed=not failures, failures=failures)
