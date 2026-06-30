from app.registry import InMemoryRegistry, flatten_records, registry_search

RECORDS = [
    {
        "id": "wmt-001", "name": "Work-Management Tool", "type": "Tool",
        "category": "Work management", "status": "In use",
        "capabilities": [
            {
                "id": "wmt-001-c02",
                "statement": "Trigger task or checklist creation from CRM deal-close events",
                "support": "native", "data_sensitivity": "Customer",
            }
        ],
    },
    {
        "id": "crm-002", "name": "CRM Platform", "type": "Tool",
        "category": "CRM", "status": "In use",
        "capabilities": [
            {
                "id": "crm-002-c01", "statement": "Store customer contact records",
                "support": "native", "data_sensitivity": "Customer",
            }
        ],
    },
]


def test_flatten_renames_and_lowercases():
    rows = flatten_records(RECORDS)
    row = next(r for r in rows if r["capability_id"] == "wmt-001-c02")
    # capability data_sensitivity (Title-Case) -> data_sensitivity_clearance (lowercase)
    assert "data_sensitivity" not in row
    assert row["data_sensitivity_clearance"] == "customer"
    assert row["status"] == "in use"
    assert row["support"] == "native"


def test_search_finds_relevant_capability():
    src = InMemoryRegistry(RECORDS)
    results = registry_search(src, "auto-create a checklist when a CRM deal closes")
    assert results, "expected at least one match"
    assert results[0]["capability_id"] == "wmt-001-c02"


def test_search_ranks_by_overlap():
    src = InMemoryRegistry(RECORDS)
    results = registry_search(src, "checklist deal-close CRM work-management")
    ids = [r["capability_id"] for r in results]
    assert ids[0] == "wmt-001-c02"  # most overlap


def test_search_empty_on_no_overlap():
    src = InMemoryRegistry(RECORDS)
    assert registry_search(src, "xylophone unicorn") == []


def test_systems_filter_contributes_tokens():
    src = InMemoryRegistry(RECORDS)
    results = registry_search(src, "store records", systems_filter=["CRM"])
    assert any(r["capability_id"] == "crm-002-c01" for r in results)
