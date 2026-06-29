#!/usr/bin/env python3
"""Validate every registry record against the schema and the registry's invariants.

This is the CI merge gate for the capability registry. It runs three layers of
checks:

1. Schema validation (JSON Schema draft 2020-12) of every record under records/.
2. Cross-record invariants the schema cannot express on its own:
   - record `id` is unique across the whole registry;
   - record `id` equals its filename stem;
   - capability `id` is unique within a record;
   - `last_verified` (and Agent `built_date`) parse as real ISO dates.
3. Drift guard: the enums in schema/record.schema.json must match the
   human-readable mirror in schema/vocabularies.yaml.

It also runs the test fixtures so all three `type` branches are exercised even
before the registry holds real records:
   - tests/schema-examples/*.yaml  MUST validate clean (positive examples);
   - tests/invalid/*.yaml          MUST each fail (proves the gate bites).

Exit code 0 = clean, 1 = at least one failure. No external services touched.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema import FormatChecker

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "record.schema.json"
VOCAB_PATH = REPO_ROOT / "schema" / "vocabularies.yaml"
RECORDS_DIR = REPO_ROOT / "records"
EXAMPLES_DIR = REPO_ROOT / "tests" / "schema-examples"
INVALID_DIR = REPO_ROOT / "tests" / "invalid"

# Maps a vocabularies.yaml key -> the matching $defs key in record.schema.json.
VOCAB_TO_DEF = {
    "type": "type",
    "status": "status",
    "discovery": "discovery",
    "category": "category",
    "support": "support",
    "sensitivity": "sensitivity",
    "cost_basis": "cost_basis",
    "model_tier": "model_tier",
}


class Findings:
    """Accumulates human-readable errors; the build fails if any are recorded."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def ok(self) -> bool:
        return not self.errors


def load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def yaml_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.rglob("*") if p.suffix in {".yaml", ".yml"}
    )


def check_vocab_drift(schema: dict, findings: Findings) -> None:
    """Schema $defs enums must equal the vocabularies.yaml mirror."""
    vocab = load_yaml(VOCAB_PATH)
    defs = schema.get("$defs", {})
    for vocab_key, def_key in VOCAB_TO_DEF.items():
        schema_enum = defs.get(def_key, {}).get("enum")
        vocab_enum = vocab.get(vocab_key)
        if schema_enum is None:
            findings.error("schema", f"$defs.{def_key}.enum is missing")
            continue
        if vocab_enum is None:
            findings.error("vocabularies.yaml", f"key '{vocab_key}' is missing")
            continue
        if schema_enum != vocab_enum:
            findings.error(
                "vocab-drift",
                f"'{vocab_key}' differs between schema ($defs.{def_key}) and "
                f"vocabularies.yaml: schema={schema_enum} vs vocab={vocab_enum}",
            )


def check_iso_date(where: str, field: str, value: object, findings: Findings) -> None:
    if not isinstance(value, str):
        return  # schema-validity is checked separately; only date-parse here
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        findings.error(where, f"{field} '{value}' is not a valid ISO date (YYYY-MM-DD)")


def validate_record_invariants(
    path: Path, record: object, findings: Findings, seen_ids: dict[str, Path]
) -> None:
    """Cross-record / cross-field checks the schema can't express."""
    where = str(path.relative_to(REPO_ROOT))
    if not isinstance(record, dict):
        return  # schema validation will already have flagged this

    record_id = record.get("id")
    if isinstance(record_id, str):
        # id must equal filename stem
        if record_id != path.stem:
            findings.error(
                where,
                f"id '{record_id}' must equal the filename stem '{path.stem}'",
            )
        # id must be unique across the registry
        if record_id in seen_ids:
            findings.error(
                where,
                f"duplicate id '{record_id}' (also in {seen_ids[record_id].relative_to(REPO_ROOT)})",
            )
        else:
            seen_ids[record_id] = path

    # capability ids unique within the record
    caps = record.get("capabilities")
    if isinstance(caps, list):
        cap_ids: set[str] = set()
        for cap in caps:
            if isinstance(cap, dict) and isinstance(cap.get("id"), str):
                cid = cap["id"]
                if cid in cap_ids:
                    findings.error(where, f"duplicate capability id '{cid}'")
                cap_ids.add(cid)

    # date fields parse as real dates
    check_iso_date(where, "last_verified", record.get("last_verified"), findings)
    if record.get("type") == "Agent":
        check_iso_date(where, "built_date", record.get("built_date"), findings)


def schema_errors(validator: Draft202012Validator, instance: object) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        out.append(f"{loc}: {err.message}")
    return out


def main() -> int:
    findings = Findings()

    if not SCHEMA_PATH.exists():
        print(f"FATAL: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1

    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    # --- drift guard -------------------------------------------------------
    check_vocab_drift(schema, findings)

    # --- live records ------------------------------------------------------
    seen_ids: dict[str, Path] = {}
    records = yaml_files(RECORDS_DIR)
    for path in records:
        where = str(path.relative_to(REPO_ROOT))
        record = load_yaml(path)
        for msg in schema_errors(validator, record):
            findings.error(where, msg)
        validate_record_invariants(path, record, findings, seen_ids)

    # --- positive fixtures (must validate clean) ---------------------------
    examples = yaml_files(EXAMPLES_DIR)
    for path in examples:
        where = str(path.relative_to(REPO_ROOT))
        errs = schema_errors(validator, load_yaml(path))
        if errs:
            for msg in errs:
                findings.error(where, f"(positive fixture should validate) {msg}")

    # --- negative fixtures (must each fail) --------------------------------
    invalids = yaml_files(INVALID_DIR)
    for path in invalids:
        where = str(path.relative_to(REPO_ROOT))
        if not schema_errors(validator, load_yaml(path)):
            findings.error(
                where, "negative fixture validated clean but was expected to FAIL"
            )

    # --- report ------------------------------------------------------------
    print(
        f"Checked {len(records)} record(s), {len(examples)} positive fixture(s), "
        f"{len(invalids)} negative fixture(s)."
    )
    if findings.ok():
        print("registry validation: PASS")
        return 0
    print(f"registry validation: FAIL ({len(findings.errors)} error(s))")
    for line in findings.errors:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
