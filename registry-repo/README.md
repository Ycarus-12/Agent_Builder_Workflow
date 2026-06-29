# Capability Registry

The GitHub-backed capability registry for the agentic tool-request workflow. It
is the canonical record of what the organization already owns — tools, built
agents, and transitional pseudo-agents — and the matchable surface that
stack-check, triage, the portfolio agent, and the registry-maintenance agent all
read.

**This repo is the registry. It is NOT the application datastore.** Request
records, pipeline state, gate decisions, and the audit log live in the
application's operational datastore, not here. (See the architecture docs in the
main build repo.)

## How it works

- **One YAML record per file**, under `records/<type>/`. The filename stem must
  equal the record's `id`.
- **PR-based change & audit trail.** Every change is a pull request; the merged
  history is the audit trail. Direct pushes to `main` are disallowed (see
  [Branch protection](#branch-protection)).
- **CI validates every record** against `schema/record.schema.json` and the
  registry's invariants before a PR can merge.

## Layout

```
records/
  tools/            # Tool records
  agents/           # Agent records (built-via-workflow)
  pseudo-agents/    # Pseudo-Agent records (Claude Projects, transitional)
schema/
  record.schema.json   # JSON Schema (draft 2020-12) — the machine gate
  vocabularies.yaml    # human-readable mirror of the controlled enums
tools/
  validate_registry.py # the CI validator (run it locally too)
  requirements.txt     # pinned validator deps
tests/
  schema-examples/     # positive fixtures — must validate (one per type)
  invalid/             # negative fixtures — must each FAIL
.github/
  workflows/registry-validate.yml
  pull_request_template.md
  CODEOWNERS
```

## The record schema (summary)

Every record carries the **shared core**: `id`, `name`, `type`, `category`,
`status`, `owner`, `data_cleared_for`, `discovery`, `last_verified`,
`capabilities`, and optional `notes`. Each entry in `capabilities` is a
**capability statement** — `id`, `statement`, `support`
(`native`/`configurable`/`not_supported`, the hinge into triage), and
`data_sensitivity`.

Type-specific fields layer on top:

| Type | Required type-specific fields |
| --- | --- |
| `Tool` | `cost_basis` (+ optional `integrations`, `admin`) |
| `Agent` | `origin: built-via-workflow`, `built_date`, `source_ref`, `model_tier`, `run_cost` |
| `Pseudo-Agent` | `origin: Claude Project`, `transitional: true` (+ optional `graduation_candidate`, `replaced_by`) |

Type-specific fields cannot leak across types — a Tool record carrying an Agent
field is rejected. The controlled vocabularies are defined in
`schema/record.schema.json` (`$defs`) and mirrored for humans in
`schema/vocabularies.yaml`; the validator fails on any drift between the two.

> **Casing note.** Registry records use Title-Case for `status` and
> `sensitivity` (per Architecture v0.3 Appendix C). The agent/orchestrator JSON
> contracts use the lowercase machine enums; the `registry_search` flatten layer
> normalizes between them (and renames capability `data_sensitivity` ->
> `data_sensitivity_clearance`). This divergence is intentional and locked — see
> the comments in `schema/vocabularies.yaml`.

See [CONTRIBUTING.md](CONTRIBUTING.md) to add or change a record.

## Validate locally

```bash
pip install -r tools/requirements.txt
python tools/validate_registry.py
```

The same command runs in CI on every PR. Exit 0 = clean.

## Branch protection

CI enforcement requires one repo setting after first push:

1. **Settings → Branches → Add branch protection rule** for `main`.
2. Enable **Require a pull request before merging** and **Require status checks
   to pass before merging**.
3. Add **`validate`** (the job in `registry-validate.yml`) as a required check.
4. Enable **Require review from Code Owners** so `CODEOWNERS` is enforced.

## First push (staging -> the registry repo)

This tree was staged in the build repo. To publish it to
`https://github.com/Ycarus-12/registry` (create the empty repo on GitHub first):

```bash
cd registry-repo
git init
git add .
git commit -m "Phase 1: registry schema, CI validation, and contributor docs"
git branch -M main
git remote add origin git@github.com:Ycarus-12/registry.git   # or the https URL
git push -u origin main
```

Then apply [Branch protection](#branch-protection).
