"""Machine-checkable assertions for cost-estimation deep-dive (cost-eval §B.2).

The deep-dive is judgment-bearing; the rubric (phase quality, pricing accuracy,
recommendation calibration) is a deferred judge-model pass (§7.2). These are the
deterministic checks: count/order vs the selected options, recommendation present
and pointing into the selection, monotone effort/USD ranges, ISO dates, and the
dollar-needs-backing rule.
"""

from __future__ import annotations

import json
import re

from .assertions import CaseResult, _is_pure_json

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ordered(low, expected, high) -> bool:
    """True when low <= expected <= high, ignoring null entries."""
    seq = [v for v in (low, expected, high) if v is not None]
    return all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))


def check_deepdive(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}

    try:
        dd = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(dd), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    directions = dd["directions"]
    selected = fixture.selected_options
    sel_ids = [o.get("option_id") for o in selected]

    if a.get("direction_count_matches_input", True) and len(directions) != len(selected):
        f.append(f"directions length {len(directions)} != selected_options {len(selected)}")
    if a.get("direction_order_preserved", True):
        for i, (d, oid) in enumerate(zip(directions, sel_ids)):
            if d["option_id"] != oid:
                f.append(f"directions[{i}].option_id {d['option_id']!r} != selected {oid!r}")

    rec = dd["recommendation"]
    if a.get("recommendation_present", True) and not rec.get("recommended_direction"):
        f.append("recommendation.recommended_direction missing")
    if a.get("recommendation_direction_in_selected", True) and rec["recommended_direction"] not in sel_ids:
        f.append(f"recommended_direction {rec['recommended_direction']!r} not among selected_options")

    # Monotone ranges + ISO dates + dollar backing, per direction.
    for d in directions:
        for ph in d["phases"]:
            if a.get("effort_low_le_expected_le_high", True) and not _ordered(
                ph["effort_low_h"], ph["effort_expected_h"], ph["effort_high_h"]
            ):
                f.append(f"{d['option_id']} phase {ph['name']!r}: effort range not low<=expected<=high")
        et = d["effort_total"]
        if a.get("effort_low_le_expected_le_high", True) and not _ordered(
            et["low_h"], et["expected_h"], et["high_h"]
        ):
            f.append(f"{d['option_id']}: effort_total not low<=expected<=high")

        if a.get("usd_low_le_expected_le_high", True):
            rc = d["run_cost"]
            if rc is not None and not _ordered(
                rc["monthly_low_usd"], rc["monthly_expected_usd"], rc["monthly_high_usd"]
            ):
                f.append(f"{d['option_id']}: run_cost monthly range not ordered")
            for key in ("first_year_total_usd", "annual_steady_state_usd"):
                r = d[key]
                if not _ordered(r["low"], r["expected"], r["high"]):
                    f.append(f"{d['option_id']}: {key} range not ordered")

        if a.get("retrieved_at_iso_dates", True):
            for obj in (d["run_cost"], d["license_cost"]):
                for src in (obj or {}).get("sources", []):
                    if not _ISO.match(src.get("retrieved_at", "")):
                        f.append(f"{d['option_id']}: retrieved_at {src.get('retrieved_at')!r} not YYYY-MM-DD")

        # every non-null priced object carries sources (schema enforces); totals lean
        # on the assumptions array (schema enforces minItems 1). This check guards
        # against a priced object with an empty sources list slipping through.
        if a.get("every_dollar_has_source_or_assumption", True):
            for obj, name in ((d["run_cost"], "run_cost"), (d["license_cost"], "license_cost")):
                if obj is not None and not obj.get("sources"):
                    f.append(f"{d['option_id']}: {name} has a dollar figure but no sources")

    return CaseResult(fixture.case_id, passed=not f, failures=f)
