# Contributing to the Capability Registry

Every change is a pull request. CI validates the registry on each PR and blocks
the merge on any failure.

## Add a record

1. Pick the type and create a file under the matching folder:
   - `records/tools/<id>.yaml`
   - `records/agents/<id>.yaml`
   - `records/pseudo-agents/<id>.yaml`
2. The **filename stem must equal the record `id`** (e.g. `wmt-001.yaml` -> `id: wmt-001`).
3. `id` is a **stable slug** (`^[a-z0-9]+(-[a-z0-9]+)*$`) and is **never reused**,
   even after deprecation.
4. Fill the shared core and the type-specific fields (see the table in
   [README](README.md#the-record-schema-summary)).
5. Write **capability statements** as problem-shaped phrases an agent can match
   to a request — not marketing features. Each needs a `support` level and a
   `data_sensitivity` clearance. Capability `id`s must be unique within the
   record (convention: `<record-id>-cNN`).
6. Validate locally before opening the PR:
   ```bash
   pip install -r tools/requirements.txt
   python tools/validate_registry.py
   ```

### Minimal Tool example

```yaml
id: wmt-001
name: Work-Management Tool
type: Tool
category: Work management
status: In use
owner: Platform team
data_cleared_for: [Internal, Customer]
discovery: Manual
last_verified: "2026-06-29"
capabilities:
  - id: wmt-001-c02
    statement: Trigger task or checklist creation from CRM deal-close events
    support: native
    data_sensitivity: Customer
cost_basis: per-seat
integrations: [REST API, Webhooks]
admin: Platform team
```

## Change an existing record

- Edit the YAML in place; the merged PR is the audit entry. Don't rename the file
  unless the `id` itself is changing (it shouldn't — ids are stable).
- Deprecating something? Set `status: Deprecated`; keep the record (and its id).
  If superseded, a Pseudo-Agent may set `replaced_by: <new-id>`.

## Add a new `category`

Categories grow demand-driven, but each addition is a reviewed change. In the
**same PR**, add the value to BOTH:

- `schema/record.schema.json` -> `$defs.category.enum`
- `schema/vocabularies.yaml` -> `category`

The validator fails if the two lists drift apart.

## What CI checks

- Schema validity (draft 2020-12) of every record.
- `id` unique across the registry; `id` equals the filename stem.
- Capability `id`s unique within a record.
- `last_verified` (and Agent `built_date`) are real ISO dates (`YYYY-MM-DD`).
- Schema enums match `vocabularies.yaml` (no drift).
- Positive fixtures still validate; negative fixtures still fail.

## A note on the test fixtures

`tests/schema-examples/` and `tests/invalid/` are **schema scaffolding, not
registry inventory**. They live outside `records/` and are never read as owned
capabilities. Leave them in place — they keep all three type branches and the
gate's failure path under test even when `records/` is sparse.
