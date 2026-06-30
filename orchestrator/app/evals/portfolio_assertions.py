"""Deterministic assertions for portfolio-pattern (portfolio-evals §, rules 1-10).

Against the supplied clusters (counts + candidate coverage + members) and pseudo-
agent usage as ground truth: tier mapping, count fidelity, noise-floor suppression,
surfacing completeness, coverage coupling + provenance, tier ordering, member
traceability, graduation grounding, pure JSON.
"""

from __future__ import annotations

import json

from .assertions import CaseResult, _is_pure_json

_TIER_RANK = {"desperate_need": 0, "likely_candidate": 1, "worth_review": 2}


def _tier_for(count: int) -> str:
    if count >= 10:
        return "desperate_need"
    if count >= 6:
        return "likely_candidate"
    return "worth_review"


def check_portfolio(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}
    clusters = {c["cluster_id"]: c for c in fixture.clusters}
    usage_ids = {u["record_id"] for u in fixture.pseudo_agent_usage}

    try:
        d = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(d), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    themes = d["themes"]
    surfaced_ids = [t["cluster_id"] for t in themes]

    for t in themes:
        cid = t["cluster_id"]
        src = clusters.get(cid)
        if src is None:
            f.append(f"theme cluster_id {cid!r} not in supplied clusters")
            continue
        count = src["request_count"]
        # 1. tier correctness; 2. count fidelity
        if t["tier"] != _tier_for(count):
            f.append(f"{cid}: tier {t['tier']!r} != {_tier_for(count)!r} for count {count}")
        if t["request_count"] != count:
            f.append(f"{cid}: request_count {t['request_count']} != supplied {count}")
        # 3. noise floor (no count 1-2 themes)
        if count < 3:
            f.append(f"{cid}: itemized a sub-threshold cluster (count {count})")
        # 5. coverage coupling
        cov = t["registry_coverage"]
        if (cov is not None) != (t["signal_type"] == "enablement"):
            f.append(f"{cid}: registry_coverage non-null must couple with signal_type enablement")
        # 6. coverage provenance
        if cov is not None:
            cand_ids = {r["record_id"] for r in src.get("candidate_coverage", [])}
            if cov["record_id"] not in cand_ids:
                f.append(f"{cid}: registry_coverage record {cov['record_id']!r} not a supplied candidate")
        # 8. member traceability
        members = {m for m in src.get("members", [])}
        for rid in t["member_request_ids"]:
            if rid not in members:
                f.append(f"{cid}: member_request_id {rid!r} not in supplied members")

    # 3/4. noise floor count + surfacing completeness
    expected_noise = sum(1 for c in fixture.clusters if c["request_count"] < 3)
    if d["noise_floor_count"] != expected_noise:
        f.append(f"noise_floor_count {d['noise_floor_count']} != {expected_noise}")
    expected_surface = {c["cluster_id"] for c in fixture.clusters if c["request_count"] >= 3}
    if set(surfaced_ids) != expected_surface or len(surfaced_ids) != len(set(surfaced_ids)):
        f.append(f"surfaced themes {sorted(surfaced_ids)} != clusters>=3 {sorted(expected_surface)}")

    # 7. ordering by tier urgency
    ranks = [_TIER_RANK[t["tier"]] for t in themes]
    if ranks != sorted(ranks):
        f.append("themes not ordered desperate_need -> likely_candidate -> worth_review")

    # 9. graduation grounding
    for g in d["pseudo_agent_graduations"]:
        if g["record_id"] not in usage_ids:
            f.append(f"graduation record {g['record_id']!r} not in supplied pseudo_agent_usage")

    return CaseResult(fixture.case_id, passed=not f, failures=f)
