"""The flatten layer (orchestrator-contract casing note, locked).

Registry records are Title-Case (Appendix C). The flatten layer normalizes
Title-Case -> lowercase and renames the capability `data_sensitivity` ->
`data_sensitivity_clearance` at the registry_search boundary, so agents see the
lowercase machine vocabulary. This is the ONLY place that rename/recasing happens.
"""

from __future__ import annotations


def flatten_record(record: dict) -> list[dict]:
    """Flatten one registry record into one searchable row per capability."""
    rows: list[dict] = []
    record_id = record.get("id", "")
    record_name = record.get("name", "")
    category = str(record.get("category", "")).lower()
    status = str(record.get("status", "")).lower()
    for cap in record.get("capabilities", []) or []:
        rows.append(
            {
                "record_id": record_id,
                "record_name": record_name,
                "category": category,
                "status": status,
                "capability_id": cap.get("id", ""),
                "capability_statement": cap.get("statement", ""),
                "support": str(cap.get("support", "")).lower(),
                # rename + lowercase: data_sensitivity -> data_sensitivity_clearance
                "data_sensitivity_clearance": str(cap.get("data_sensitivity", "")).lower(),
            }
        )
    return rows


def flatten_records(records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        rows.extend(flatten_record(record))
    return rows
