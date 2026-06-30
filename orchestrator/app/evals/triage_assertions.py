"""Deterministic cross-field assertions for triage (triage-evals §, rules 1-11).

Validates the option list, route-field coupling, recommendation referential
integrity, configure provenance/evidence floor, cascade-trace integrity, and the
sensitivity overlay against the case's intake_record + stack_check_result.
"""

from __future__ import annotations

import json

from .assertions import CaseResult, _is_pure_json

# Cascade gates in order; the trace must be a contiguous prefix of this list.
GATE_ORDER = (
    "Belongs to another function?",
    "Worth solving?",
    "Does a tool we own fit?",
    "Process or training gap?",
    "Does buying beat building?",
    "Otherwise build",
)
GATE_TO_OUTCOME = {
    "Belongs to another function?": "route_elsewhere",
    "Worth solving?": "dont_build",
    "Does a tool we own fit?": "configure",
    "Process or training gap?": "process_training_fix",
    "Does buying beat building?": "buy",
    "Otherwise build": "build",
}
_NULL_OUTCOMES = {"route_elsewhere", "dont_build", "process_training_fix"}
_OPTION_OUTCOMES = {"configure", "build", "buy"}


def _nn(v) -> bool:
    return v is not None


def check_triage(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}
    scr = fixture.stack_check_result or {}
    intake = fixture.intake_record or {}

    try:
        out = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(out), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:  # schema-invalid: cross-field checks would be noise
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    options = out["options"]
    option_ids = [o["option_id"] for o in options]
    rec = out["recommendation"]
    outcome = rec["outcome"]

    # 1. unique option ids
    if len(option_ids) != len(set(option_ids)):
        f.append("duplicate option_id in options")

    # 2. route-field coupling
    for o in options:
        route = o["route"]
        cfg = (_nn(o["tool_name"]) and _nn(o["capability_id"]))
        bld = (_nn(o["avenue"]) and _nn(o["engine"]) and _nn(o["weight"]))
        buy = (_nn(o["vendor_or_category"]) and _nn(o["bought_capability"]))
        cfg_any = _nn(o["tool_name"]) or _nn(o["capability_id"])
        bld_any = _nn(o["avenue"]) or _nn(o["engine"]) or _nn(o["weight"])
        buy_any = _nn(o["vendor_or_category"]) or _nn(o["bought_capability"])
        if route == "configure" and not (cfg and not bld_any and not buy_any):
            f.append(f"option {o['option_id']}: configure must set tool_name+capability_id only")
        if route == "build" and not (bld and not cfg_any and not buy_any):
            f.append(f"option {o['option_id']}: build must set avenue+engine+weight only")
        if route == "buy" and not (buy and not cfg_any and not bld_any):
            f.append(f"option {o['option_id']}: buy must set vendor_or_category+bought_capability only")

    # 4. recommendation null-rule + referential integrity
    rid = rec["recommended_option_id"]
    if outcome in _NULL_OUTCOMES and rid is not None:
        f.append(f"recommended_option_id must be null for outcome {outcome}")
    if outcome in _OPTION_OUTCOMES:
        if rid is None:
            f.append(f"recommended_option_id must be non-null for outcome {outcome}")
        elif rid not in option_ids:
            f.append(f"recommended_option_id {rid!r} not in options")
        else:
            chosen = next(o for o in options if o["option_id"] == rid)
            if chosen["route"] != outcome:
                f.append(f"recommended option route {chosen['route']!r} != outcome {outcome!r}")

    # 5. alternatives integrity
    for alt in rec["alternatives"]:
        if alt["option_id"] not in option_ids:
            f.append(f"alternative {alt['option_id']!r} not in options")
        if alt["option_id"] == rid:
            f.append("alternative equals recommended_option_id")

    # 6. destination_team coupling
    if (rec["destination_team"] is not None) != (outcome == "route_elsewhere"):
        f.append("destination_team must be non-null iff outcome is route_elsewhere")

    # 7. configure provenance + 8. evidence floor
    match_cap_ids = {m.get("capability_id") for m in scr.get("matches", [])}
    has_configure = any(o["route"] == "configure" for o in options)
    for o in options:
        if o["route"] == "configure" and o["capability_id"] not in match_cap_ids:
            f.append(f"configure option {o['option_id']}: capability_id not in stack_check matches")
    if has_configure and (scr.get("registry_confidence") == "empty" or scr.get("no_existing_coverage") is True):
        f.append("configure option present despite empty/no-coverage stack-check result")

    # 9. trace integrity
    trace = out["cascade_trace"]
    for i, entry in enumerate(trace):
        if i >= len(GATE_ORDER) or entry["gate"] != GATE_ORDER[i]:
            f.append(f"cascade_trace[{i}].gate {entry['gate']!r} breaks cascade order")
            break
    resolved_idx = [i for i, e in enumerate(trace) if e["resolved"]]
    if resolved_idx != [len(trace) - 1]:
        f.append(f"exactly one resolved gate expected as the last entry; got resolved at {resolved_idx}")
    elif GATE_TO_OUTCOME.get(trace[-1]["gate"]) != outcome:
        f.append(f"final gate {trace[-1]['gate']!r} does not map to outcome {outcome!r}")

    # 10. sensitivity overlay
    eff = out["sensitivity_overlay"]["effective_sensitivity"]
    if eff != intake.get("data_sensitivity"):
        f.append(f"effective_sensitivity {eff!r} != intake data_sensitivity {intake.get('data_sensitivity')!r}")

    # expected outcome (per-case)
    if "expected_outcome" in a and outcome != a["expected_outcome"]:
        f.append(f"outcome {outcome!r} != expected {a['expected_outcome']!r}")

    return CaseResult(fixture.case_id, passed=not f, failures=f)
