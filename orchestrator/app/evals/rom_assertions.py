"""Deterministic assertions for cost-estimation ROM (cost-estimation-evals §A.2).

Schema validity (the route band rules live in the schema's conditional blocks) plus:
option count/order vs the input list, key-driver count, per-case field assertions,
and the no-dollar / no-timeline / no-cross-option-recommendation cleanliness checks
(scoped to ROM's authored prose: estimate_summary + key_drivers).
"""

from __future__ import annotations

import json
import re

from .assertions import CaseResult, _is_pure_json

_DOLLAR = re.compile(r"\$|\busd\b|\bdollars?\b|\b\d+\s?(?:k|m)\b", re.IGNORECASE)
_TIMELINE = re.compile(
    r"\b(?:weeks?|days?|months?|years?|quarters?)\b|\bby (?:next|end of)\b|\bq[1-4]\b",
    re.IGNORECASE,
)
_CROSS_OPTION = re.compile(
    r"\brecommend|\bbest option|\bgo with\b|\bpick (?:option|the)|\bchoose (?:option|the)|\bshould (?:pick|choose|go)",
    re.IGNORECASE,
)


def _authored_prose(rom: dict) -> str:
    parts = [rom.get("estimate_summary", "")]
    for opt in rom.get("costed_options", []):
        parts.extend(opt.get("key_drivers", []))
    return " ".join(parts)


def check_rom(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}

    try:
        rom = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(rom), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    costed = rom["costed_options"]
    inputs = fixture.option_list

    if a.get("option_count_matches_input", True) and len(costed) != len(inputs):
        f.append(f"costed_options length {len(costed)} != input options {len(inputs)}")

    if a.get("option_order_preserved", True):
        for i, (c, inp) in enumerate(zip(costed, inputs)):
            if c["option_id"] != inp.get("option_id"):
                f.append(f"costed_options[{i}].option_id {c['option_id']!r} != input {inp.get('option_id')!r}")

    if a.get("key_drivers_count_in_range", True):
        for c in costed:
            if not (2 <= len(c["key_drivers"]) <= 3):
                f.append(f"{c['option_id']}: key_drivers count {len(c['key_drivers'])} not in 2..3")

    prose = _authored_prose(rom)
    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")
    if a.get("no_dollar_figures", True) and _DOLLAR.search(prose):
        f.append("dollar/currency figure in ROM prose")
    if a.get("no_timeline_language", True) and _TIMELINE.search(prose):
        f.append("timeline/duration language in ROM prose")
    if a.get("no_cross_option_recommendation", True) and _CROSS_OPTION.search(rom.get("estimate_summary", "")):
        f.append("estimate_summary contains a cross-option recommendation")

    # Per-case field assertions: {option_id: {field: expected_value}}
    by_id = {c["option_id"]: c for c in costed}
    for opt_id, expected in (a.get("field_assertions") or {}).items():
        if opt_id not in by_id:
            f.append(f"field_assertions reference unknown option {opt_id!r}")
            continue
        for field, val in expected.items():
            if by_id[opt_id].get(field) != val:
                f.append(f"{opt_id}.{field} {by_id[opt_id].get(field)!r} != {val!r}")

    return CaseResult(fixture.case_id, passed=not f, failures=f)
