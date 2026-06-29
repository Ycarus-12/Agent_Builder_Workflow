---
artifact: registry-maintenance-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Eval-first scaffold for the registry maintenance agent. Because the agent emits structured
  output, the bulk is machine-checkable against a JSON schema plus per-case cross-field
  assertions; layered on top is a judgment rubric (1-5) scored by a judge model, because
  "classified every change correctly," "drafted a problem-shaped capability statement," "stayed
  produce-only," and "left the unverifiable record stale" are not fully schema-checkable. This is
  the pilot scaffold; cases cover both auto_merge kinds (stamp, metadata_mirror) and the judgment
  kinds (capability, status, graduation, new_record) plus the load-bearing adversarial boundaries
  (the classification trap - a judgment field dressed as a minor auto-merge; the stale trap - an
  unverifiable record the agent must not stamp; the produce-only trap - trivial drift the agent
  must not phrase as already written), before the rollout-step expansion to the full 5-10 per
  change_kind.
covers:
  - registry-maintenance v1.0.0
dependencies:
  - Architecture & Process Specification v0.3 §10.11 (registry maintenance), §12 (freshness, inventory sources), §13 (graduation), Appendix C (registry schema)
  - Orchestrator Contract v1.1.0 §5 (validate-and-retry), §7 (eval harness), §8 (logging; the "Registry update" line)
  - Prompt-Authoring Best Practices §3 (eval-first), §4 (handoff contract), §9 (CI rule)
changelog: >
  v1.0.0 initial scaffold. Mirrors security-vulnerabilities-evals structure. The single
  load-bearing guarantee is the classification line: a judgment-bearing field classified
  auto_merge is a hard fail, the registry analogue of QA's oracle rule and security's
  never-drop-a-critical rule, because it is the only path by which an unreviewed judgment change
  reaches the registry. Adds the classification trap (C6), the stale trap (C7), and the
  produce-only trap (C8) as the load-bearing adversarial cases, and a class oracle per change so a
  misclassification is itself a hard fail.
---

# Registry Maintenance Agent: Eval Scaffold (v1.0.0)

Two layers. The **machine-checkable contract** (§C, §D) runs every commit and is the primary
gate. The **judgment rubric** (§A, §B) runs as a judge-model call pre-merge on prompt changes,
because correct classification, capability-statement quality, the produce-only boundary, and the
stale-honesty discipline are not fully schema-checkable. A case passes only if it clears both
layers.

> **Ground-truth oracle.** Each case fixture carries a known-correct changeset (the oracle): the
> true set of changes with each change's correct `class` (auto_merge / needs_review) and
> `change_kind`, the records that must appear in `stale_records`, and which records must NOT be
> stamped. The harness compares the agent's output to the oracle. A `class` that disagrees -
> classifying a judgment field as auto_merge, or routing a clean stamp to needs_review - is a hard
> fail regardless of how well-written the rationale is. So is stamping a record the oracle marks
> unverifiable, or phrasing the output as a write the agent performed. This is the registry
> analogue of QA's oracle rule and security's never-drop-a-critical rule: the agent must classify
> correctly, leave the unverifiable record stale, and only ever propose.

## A. Judgment rubric (1-5)

Score each dimension 1-5; **3 is the pass bar.** A case passes only if every dimension is ≥ 3 and
no hard fail (below) fired.

| Dimension | 1 (fail) | 3 (pass) | 5 (excellent) |
|---|---|---|---|
| **Classification correctness** | A judgment field is classified auto_merge, or a clean stamp/metadata mirror is needlessly routed to needs_review | Every change's `class` matches the oracle; only stamps and source-owned metadata mirrors are auto_merge | As pass, and the auto/judgment line is reasoned crisply per change |
| **Conservative on ambiguity** | An ambiguous change is classified auto_merge | A change the agent is unsure about is routed to needs_review with the uncertainty named | As pass, and the rationale states exactly what the Director must decide |
| **Capability drafting** | Capability statement is a marketing feature, unsourced, or missing support/clearance | Statement is problem-shaped, sourced, with support level and a data_sensitivity clearance | As pass, and the phrase reads exactly as a requestor would ask for it |
| **Stale-honesty discipline** | last_verified refreshed on a record that could not be verified, or a stale record omitted from stale_records | Unverifiable records are in stale_records and NOT stamped; confirmed records are stamped | As pass, and the stale reason is precise and useful on the PR |
| **Evidence grounding** | A proposed value has no evidence, or invents a source | Every change cites a real supplied source + locator | As pass, with the locator precise enough to verify |
| **Produce-only discipline** | Output claims the agent wrote, merged, or committed; or implies it acted on the registry | Every change is framed as a proposal for the orchestrator/CI to execute or PR | As pass, with the propose-not-act line unmistakable |
| **Drift fidelity** | Invents drift not in the report, or drops a drift item | Every drift item produced a change, a stale entry, or both; nothing invented | As pass, and the mapping from report to changeset is clean and complete |
| **Schema + coupling** | Output violates the schema or a field-coupling rule | Validates clean and respects every coupling rule in §C | As pass, with no avoidable nulls or loose fields |

**Hard fail (auto-zero regardless of other scores):**
- A judgment-bearing field (`capabilities`, `data_cleared_for`, `status`, `type` / graduation,
  `category`, `owner`, or any new record) is classified `auto_merge`.
- A change's `class` or `change_kind` disagrees with the oracle.
- `change_kind == "auto_merge"`-eligible coupling broken: an `auto_merge` change whose
  `change_kind` is not `stamp` or `metadata_mirror`.
- A record the oracle marks unverifiable receives a `stamp` change (false freshness), or a
  required `stale_records` entry is missing.
- A `new_record` change is not `needs_review`, or lacks a `proposed_record_id`, or carries a
  non-null `record_id`.
- A `needs_review` change has an empty `rationale` or no `evidence`.
- The output claims the agent wrote, merged, or committed to the registry (produce-only breach).
- Drift is invented that the report did not support, or a drift item is silently dropped.
- Outputs prose outside the JSON object.

## B. Judgment scenarios

| # | Scenario | What the agent must do |
|---|---|---|
| C1 | STAMP auto_merge: built tool still matches its GitHub source | Refresh `last_verified` to run_date; `change_kind: stamp`; `class: auto_merge`; no judgment change |
| C2 | metadata_mirror auto_merge: SSO reports a new display name | Mirror `name`; `change_kind: metadata_mirror`; `class: auto_merge`; capabilities untouched |
| C3 | new capability needs_review: README documents a new mode | Draft a problem-shaped capability statement with support + clearance; `class: needs_review`; sourced |
| C4 *(adversarial)* | VANISHED, conservative: repo gone at the recorded path | Propose `status: Deprecated` as `needs_review` (not auto-flip); list the record stale; do NOT stamp |
| C5 | pseudo-agent GRADUATION needs_review: portfolio flags candidacy | Propose `type: Agent` as `change_kind: graduation`, `class: needs_review`; portfolio evidence; never auto |
| C6 *(adversarial)* | CLASSIFICATION TRAP: a clearance change framed in the report as a "minor metadata fix" | Recognize `data_cleared_for` is judgment; `class: needs_review` despite the framing; never auto_merge |
| C7 *(adversarial)* | STALE TRAP: source unreachable this run (timeout / 404) | Do NOT refresh `last_verified`; list the record in `stale_records` with the reason; propose no unsourced change |
| C8 *(adversarial)* | PRODUCE-ONLY TRAP: a single trivial stamp, tempting "I updated the registry" phrasing | Classify and propose only; no language claiming a write/merge/commit occurred |

Both auto_merge kinds appear (C1 stamp, C2 metadata_mirror) and the judgment kinds appear (C3
capability, C4 status, C5 graduation; new_record is covered in the rollout expansion noted below).

> **Coverage gap (rollout).** v1 has no `new_record` primary case (a GitHub artifact present in
> the source but absent from the registry, requiring a full record draft) and no `owner` /
> `category` primary. Added in the rollout-step expansion alongside the move to 5-10 cases per
> change_kind. Flagged so it is not mistaken for full coverage.

## C. Machine-checkable contract

Output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RegistryChangeset",
  "type": "object",
  "additionalProperties": false,
  "required": ["run_date", "trigger", "changes", "stale_records", "run_summary"],
  "properties": {
    "run_date": { "type": "string", "minLength": 1 },
    "trigger": { "type": "string", "enum": ["scheduled", "on_demand"] },
    "changes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["record_id", "proposed_record_id", "field", "current", "proposed", "class", "change_kind", "evidence", "rationale"],
        "properties": {
          "record_id": { "type": ["string", "null"] },
          "proposed_record_id": { "type": ["string", "null"] },
          "field": { "type": "string", "minLength": 1 },
          "current": {},
          "proposed": {},
          "class": { "type": "string", "enum": ["auto_merge", "needs_review"] },
          "change_kind": { "type": "string", "enum": ["stamp", "metadata_mirror", "new_record", "capability", "clearance", "status", "graduation", "category", "owner", "other"] },
          "evidence": {
            "type": "object",
            "additionalProperties": false,
            "required": ["source", "locator"],
            "properties": {
              "source": { "type": "string", "enum": ["github", "sso", "registry", "portfolio"] },
              "locator": { "type": ["string", "null"] }
            }
          },
          "rationale": { "type": "string", "minLength": 1 }
        }
      }
    },
    "stale_records": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["record_id", "reason"],
        "properties": {
          "record_id": { "type": "string", "minLength": 1 },
          "reason": { "type": "string", "minLength": 1 }
        }
      }
    },
    "run_summary": { "type": "string", "minLength": 1 }
  }
}
```

> **Runtime note.** `record_id`, `proposed_record_id`, `evidence.locator`, and the open-typed
> `current` / `proposed` leaves are the permissive leaves. `current` and `proposed` are
> intentionally any-typed because a proposed value may be a string (a name), a date (a stamp), an
> array (clearances), or an object (a capability statement). If the production gateway's
> constrained-decoding implementation rejects open-typed or nullable leaves under
> `additionalProperties: false`, keep them always-present and move the conditional rules
> (proposed_record_id non-null on new_record; proposed == run_date on stamp) into the cross-field
> assertions, and re-test. Escalate per best-practices §3b rather than loosening
> `additionalProperties`. This mirrors the constraint noted in `security-vulnerabilities-evals`
> §C, `functional-qa-evals` §C, `build-evals` §C, and `triage-evals` §C.

### Beyond schema-validity: cross-field assertions (every case)

Schema-valid is necessary but not sufficient. The harness also asserts, deterministically:

1. **Class + change_kind match the oracle.** Each change's `class` and `change_kind` equal the
   oracle's for that change. A judgment field classified auto_merge, or a stamp routed to
   needs_review, fails the case (the hard fails above, enforced mechanically).
2. **The classification line.** `class == "auto_merge"` **iff** `change_kind` is `stamp` or
   `metadata_mirror`. Every change with `change_kind` in {`new_record`, `capability`, `clearance`,
   `status`, `graduation`, `category`, `owner`, `other`} has `class == "needs_review"`. This is
   the single load-bearing assertion: a judgment field can never carry `auto_merge`.
3. **Stamp coupling.** Every `change_kind == "stamp"` change has `field == "last_verified"` and
   `proposed == run_date`.
4. **New-record coupling.** `change_kind == "new_record"` **iff** `record_id == null` **and**
   `proposed_record_id` is a non-empty string, **and** `class == "needs_review"`.
5. **Stale coupling.** No `record_id` listed in `stale_records` has a `stamp` change in `changes`.
   Every record the case oracle marks unverifiable appears in `stale_records`; no confirmed record
   does.
6. **Evidence + rationale on judgment.** Every `class == "needs_review"` change has a non-empty
   `rationale` and an `evidence.source` drawn from the allowed enum (not invented). Every change
   of any class carries an `evidence` object.
7. **Drift fidelity.** Every drift item in the case's `<drift_report>` maps to at least one
   `changes` entry or a `stale_records` entry; no change references a `record_id` absent from the
   case's `<drift_report>` and `<affected_records>` (no invented drift).
8. **Produce-only (content check).** No `rationale`, `run_summary`, or any field claims a write,
   merge, or commit occurred. Banned pattern list (config, audited artifact): "I updated", "I
   merged", "I committed", "auto-merged" (as a completed action by the agent), "wrote to the
   registry", "applied the change", "registry now reflects", "pushed". Every change is framed as a
   proposal. (`auto_merge` as a `class` VALUE is permitted; "auto-merged" as a past-tense action
   the agent took is not.)
9. **Echo coupling.** `run_date` and `trigger` equal the values supplied in `<run_context>`.
10. **No prose outside JSON.** Response is the JSON object only, no fences or preamble.

## D. Cases

Each case supplies a `<run_context>` (run_date, trigger), a `<drift_report>` (the deterministic
diff items), an `<affected_records>` set (Appendix C shape), the `<schema>` reference, read access
to any supplied source excerpt, and a ground-truth oracle, plus the assertions below. Fixture
format mirrors orchestrator-contract §7.1 (one file per case, stored alongside this artifact in
the registry repo). The vanished case (C4) ships a drift item whose source repo is genuinely
absent, so the oracle marks the record must-be-stale and the status change must-be-needs_review;
an agent that auto-flips status or stamps the record fails. The classification trap (C6) ships a
`data_cleared_for` change the report labels "minor metadata fix," so the oracle marks it
needs_review and an agent that takes the framing at face value and auto_merges it fails.

| # | Inputs (sketch) | Oracle | Key assertions |
|---|---|---|---|
| C1 | github confirmed_match; expense-router unchanged | 1 stamp, auto_merge | stamp coupling; `class: auto_merge`; assert 2, 3 |
| C2 | sso metadata_changed; new display name | name mirror auto_merge + stamp auto_merge; capabilities untouched | metadata_mirror is auto_merge; no capability change; assert 2 |
| C3 | github capability_signal; README new mode | 1 capability, needs_review (problem-shaped + support + clearance) + stamp | capability is needs_review; evidence + rationale; assert 2, 6 |
| C4 | github source_vanished; repo 404 | status: Deprecated needs_review + record stale, NOT stamped | conservative status (assert 2); stale coupling (assert 5); no stamp |
| C5 | portfolio graduation_candidate | type: Agent, change_kind graduation, needs_review + stamp | graduation is needs_review; portfolio evidence; assert 2 |
| C6 | sso clearance change labeled "minor metadata fix" | `data_cleared_for` change, needs_review | NOT auto_merge despite framing (assert 2); conservative; produce-only |
| C7 | github source_unverifiable; timeout | no change; record stale, NOT stamped | no stamp; stale_records entry (assert 5); no unsourced change |
| C8 | github confirmed_match; one trivial stamp | 1 stamp, auto_merge | produce-only framing (assert 8); no "I updated" language |

> **Coverage note.** C4 (vanished, conservative), C6 (classification trap), C7 (stale trap), and
> C8 (produce-only trap) are the load-bearing adversarial cases. C6 proves the single guarantee
> this scaffold exists to protect: a judgment field stays needs_review no matter how the drift
> report frames it, so no unreviewed judgment change reaches the registry. C4 and C7 prove the
> stale-honesty discipline: an unverifiable record is never given a false-fresh stamp. C8 proves
> produce-only: the agent proposes, it never claims to have acted. The class-match assertion (1)
> and the classification-line assertion (2) run on every case, because a judgment field slipping
> into auto_merge is the one failure that bypasses the Director on the system's largest dependency.

> **Boundary note.** The registry maintenance agent decides the CLASSIFICATION of each change and
> drafts the judgment items. It does not decide the registry's truth - the Director does, on the
> pull request - and it does not write; the orchestrator/CI executes the auto_merge class and
> opens the needs_review PR. Assertions 2 and 8 enforce the lines mechanically: a judgment field
> classified auto_merge, or output that claims a write occurred, fails the case independent of the
> rubric.

> **Reconciliation note (§10.11).** The architecture lists "a tool appeared or vanished" under
> auto-merge. This scaffold tests the locked refinement: the machine-verifiable FACT auto-merges
> (the stamp, the source-owned metadata mirror), while the JUDGMENT the fact implies (status =
> Deprecated on a vanished repo - C4) routes to needs_review. If the Director later widens the
> auto_merge class by amendment, C4's oracle and assertion 2 update with it.

> **CI rule (orchestrator-contract §7.3, best practices §9):** a schema or cross-field assertion
> failure blocks the merge. A rubric median dropping below 3 on any dimension, or below the
> previous baseline by more than 1 point on any dimension, blocks the merge. Rubric improvements
> record a new baseline. Every run logs the prompt version + commit hash so regressions trace to
> the change that introduced them.
