"""Deterministic assertions for registry-maintenance (registry-evals §, rules 1-10).

The classification line (auto_merge iff stamp/metadata_mirror), stamp/new-record
coupling, stale coupling, evidence on judgment, drift fidelity vs the supplied
report, the produce-only content check (proposes; never claims a write), echo of
run_context, and pure JSON.
"""

from __future__ import annotations

import json

from .assertions import CaseResult, _is_pure_json

_AUTO_KINDS = {"stamp", "metadata_mirror"}
_BANNED_WRITE = (
    "i updated", "i merged", "i committed", "auto-merged", "wrote to the registry",
    "applied the change", "registry now reflects", "pushed",
)


def _contains_banned(text: str) -> str | None:
    low = text.lower()
    for n in _BANNED_WRITE:
        if n in low:
            return n
    return None


def check_registry_maintenance(fixture, raw_output: str, schema: dict) -> CaseResult:
    from jsonschema import Draft202012Validator

    f: list[str] = []
    a = fixture.assertions or {}
    ctx = fixture.run_context or {}
    drift_ids = {item["record_id"] for item in fixture.drift_report if item.get("record_id")}
    allowed_ids = drift_ids | set(fixture.affected_records)
    oracle = fixture.oracle or {}

    try:
        cs = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        return CaseResult(fixture.case_id, False, [f"output is not valid JSON: {exc.msg}"])

    for err in sorted(Draft202012Validator(schema).iter_errors(cs), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        f.append(f"schema: {loc}: {err.message}")
    if f:
        return CaseResult(fixture.case_id, False, f)

    if a.get("no_prose_outside_json", True) and not _is_pure_json(raw_output):
        f.append("output is not pure JSON")

    changes = cs["changes"]
    run_date = cs["run_date"]

    # 9. echo coupling
    if "run_date" in ctx and run_date != ctx["run_date"]:
        f.append(f"run_date {run_date!r} != run_context {ctx['run_date']!r}")
    if "trigger" in ctx and cs["trigger"] != ctx["trigger"]:
        f.append(f"trigger {cs['trigger']!r} != run_context {ctx['trigger']!r}")

    # 1. class+change_kind match oracle (if provided, aligned to change order)
    oracle_changes = oracle.get("changes", [])
    if oracle_changes and len(oracle_changes) == len(changes):
        for i, (ch, exp) in enumerate(zip(changes, oracle_changes)):
            if ch["change_kind"] != exp.get("change_kind") or ch["class"] != exp.get("class"):
                f.append(
                    f"change[{i}] ({ch['change_kind']},{ch['class']}) != oracle "
                    f"({exp.get('change_kind')},{exp.get('class')})"
                )

    for i, ch in enumerate(changes):
        kind, cls = ch["change_kind"], ch["class"]
        # 2. the classification line
        expect_auto = kind in _AUTO_KINDS
        if (cls == "auto_merge") != expect_auto:
            f.append(f"change[{i}] {kind}: class must be auto_merge iff stamp/metadata_mirror")
        # 3. stamp coupling
        if kind == "stamp" and not (ch["field"] == "last_verified" and ch["proposed"] == run_date):
            f.append(f"change[{i}] stamp: field must be last_verified and proposed == run_date")
        # 4. new_record coupling
        is_new = kind == "new_record"
        new_shape = ch["record_id"] is None and bool(ch["proposed_record_id"]) and cls == "needs_review"
        if is_new != new_shape:
            f.append(f"change[{i}]: new_record iff (record_id null, proposed_record_id set, needs_review)")
        # 6. evidence + rationale on judgment
        if cls == "needs_review" and not ch["rationale"].strip():
            f.append(f"change[{i}]: needs_review requires a non-empty rationale")
        # 7. drift fidelity (no change references a record outside drift+affected)
        if ch["record_id"] is not None and ch["record_id"] not in allowed_ids:
            f.append(f"change[{i}]: record_id {ch['record_id']!r} not in drift_report/affected_records")
        # 8. produce-only
        hit = _contains_banned(ch["rationale"])
        if hit:
            f.append(f"change[{i}]: produce-only violation (claims a write): '{hit}'")

    # 5. stale coupling: no stale record has a stamp change
    stamped = {ch["record_id"] for ch in changes if ch["change_kind"] == "stamp"}
    for sr in cs["stale_records"]:
        if sr["record_id"] in stamped:
            f.append(f"stale record {sr['record_id']!r} also has a stamp change")

    # 8. produce-only in run_summary
    hit = _contains_banned(cs["run_summary"])
    if hit:
        f.append(f"run_summary produce-only violation: '{hit}'")

    return CaseResult(fixture.case_id, passed=not f, failures=f)
