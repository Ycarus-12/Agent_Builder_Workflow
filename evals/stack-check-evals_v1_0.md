---
artifact: stack-check-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-26
purpose: >
  Eval scaffold for the stack-check agent. All cases are machine-checkable
  against the JSON schema and per-case assertions; no subjective rubric is
  needed for a retrieval-and-classification agent. Each case includes a
  registry mock fixture specifying what registry_search returns for that
  scenario. This is the pilot scaffold; expand as the registry grows and new
  coverage patterns emerge (multi-match, mixed support levels, regulated-data
  clearance).
covers:
  - stack-check v1.0.0
dependencies:
  - Prompt-Authoring Best Practices §3 (eval-first), §6 (orchestrator contract), §8 (rollout)
  - orchestrator-contract v1.1.0 §7 (eval harness shape)
changelog: v1.0.0 initial scaffold.
---

# Stack-Check Agent: Eval Scaffold (v1.0.0)

## A. Machine-checkable contract

The stack-check output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "StackCheckFinding",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "request_title", "matches", "no_existing_coverage",
    "registry_confidence", "finding_summary", "systems_searched"
  ],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "matches": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "record_id", "record_name", "capability_id", "capability_statement",
          "support", "data_sensitivity_clearance", "relevance_note"
        ],
        "properties": {
          "record_id":                  { "type": "string" },
          "record_name":                { "type": "string" },
          "capability_id":              { "type": "string" },
          "capability_statement":       { "type": "string" },
          "support": {
            "type": "string",
            "enum": ["native", "configurable", "not_supported"]
          },
          "data_sensitivity_clearance": { "type": "string" },
          "relevance_note":             { "type": "string" }
        }
      }
    },
    "no_existing_coverage": { "type": "boolean" },
    "registry_confidence": {
      "type": "string",
      "enum": ["high", "low", "empty"]
    },
    "finding_summary":  { "type": "string", "minLength": 1 },
    "systems_searched": { "type": "array", "items": { "type": "string" } }
  }
}
```

### Beyond schema-validity: assertions per case

Schema-valid is necessary but not sufficient. Each case also asserts:

1. **No invented matches.** Every item in `matches` traces verbatim to a record in
   the fixture's `registry_mock.response`. The agent must not invent a match not
   returned by the stub.
2. **All mock matches present.** Every record in `registry_mock.response` must appear
   in `matches` by `capability_id`. None may be silently dropped.
3. **Sensitivity floor correct.** The effective floor from the step 3 mapping was
   applied. For `"unspecified"`, floor = `"customer"`. Treating "unspecified" as
   "none" or "internal" is a fail.
4. **`no_existing_coverage` correct.** Applied the two-condition rule: `false` only
   when at least one match has support = `native` or `configurable` AND clearance ≥
   effective floor.
5. **`registry_confidence` correct.** Applied the three-bucket rubric from task
   step 8 exactly.
6. **No recommendation language.** `finding_summary` and all `relevance_note` fields
   contain no routing or outcome language (e.g., "should configure", "should build",
   "recommend", "suggests buying").
7. **No prose outside JSON.** Output is the JSON object only; no preamble, summary,
   or markdown fences.

## B. Hard fails (auto-fail regardless of other assertions)

- Output contains a routing recommendation or outcome in any field.
- Sensitivity floor applied incorrectly — especially `"unspecified"` mapped to
  anything below `"customer"`.
- `registry_search` called more than once for the request.
- Any record from `registry_mock.response` absent from `matches`.
- Output includes any text outside the JSON object.

## C. Cases

Each fixture specifies the intake record input, the mock registry response (what
the stub returns when `registry_search` is called regardless of the exact query
string), and per-case assertions.

---

### S1 — Native match, high confidence (happy path)

```yaml
case_id: S1
agent: stack-check
version: 1.0.0
description: >
  Native-support match; clearance meets the sensitivity floor. Clean coverage
  finding. The happy path the registry is designed to enable.
intake_record:
  request_title: "Auto-create kickoff checklist on deal close"
  problem_outcome: >
    When a deal closes in the CRM, a kickoff checklist needs to be created in
    the work-management tool automatically.
  current_workaround: "Created manually each time a deal closes, ~20 minutes."
  systems_involved: ["CRM", "work-management tool"]
  data_sensitivity: "customer"
  customer_facing: false
  # remaining fields null / default
registry_mock:
  response:
    - record_id: "wmt-001"
      record_name: "Work-Management Tool"
      capability_id: "wmt-001-c02"
      capability_statement: "Trigger task or checklist creation from CRM deal-close events"
      support: "native"
      data_sensitivity_clearance: "customer"
assertions:
  schema_valid: true
  no_existing_coverage: false
  registry_confidence: "high"
  all_mock_matches_present: true
  matches_length: 1
  matches_0_support: "native"
  sensitivity_floor_applied: "customer"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["CRM", "work-management tool"]
  expected_query_contains:
    - "checklist"
    - "CRM"
    - "work-management tool"
```

---

### S2 — Configurable match, high confidence

```yaml
case_id: S2
agent: stack-check
version: 1.0.0
description: >
  One configurable-support match; clearance meets the floor. The need can be
  met by configuring an owned tool; no_existing_coverage is false.
intake_record:
  request_title: "Track billable hours against projects in project management tool"
  problem_outcome: >
    The team tracks billable hours in a separate spreadsheet; they want to log
    hours directly against projects inside the project management tool.
  current_workaround: "Maintained manually in a shared spreadsheet each Friday."
  systems_involved: ["project management tool", "spreadsheets"]
  data_sensitivity: "internal"
  customer_facing: false
registry_mock:
  response:
    - record_id: "pmt-001"
      record_name: "Project Management Tool"
      capability_id: "pmt-001-c05"
      capability_statement: "Log and report time entries against projects and tasks"
      support: "configurable"
      data_sensitivity_clearance: "internal"
assertions:
  schema_valid: true
  no_existing_coverage: false
  registry_confidence: "high"
  all_mock_matches_present: true
  matches_length: 1
  matches_0_support: "configurable"
  sensitivity_floor_applied: "internal"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["project management tool", "spreadsheets"]
  expected_query_contains:
    - "billable hours"
    - "project management tool"
```

---

### S3 — Explicit no-coverage (not_supported match)

```yaml
case_id: S3
agent: stack-check
version: 1.0.0
description: >
  The registry has an entry for the relevant system, and the capability has been
  explicitly evaluated and recorded as not_supported. This is a stronger
  no-coverage signal than an empty registry — the tool was checked and cannot
  do it. The match must appear in output; no_existing_coverage must be true.
intake_record:
  request_title: "Automated customer notifications on ticket close"
  problem_outcome: >
    When a support ticket closes, the assigned customer should automatically
    receive an email notification without a manual step from the support agent.
  current_workaround: "Support agents send a manual follow-up email after closing."
  systems_involved: ["support tool"]
  data_sensitivity: "customer"
  customer_facing: true
registry_mock:
  response:
    - record_id: "spt-001"
      record_name: "Support Tool"
      capability_id: "spt-001-c03"
      capability_statement: "Send automated outbound email notifications to customers on ticket events"
      support: "not_supported"
      data_sensitivity_clearance: "customer"
assertions:
  schema_valid: true
  no_existing_coverage: true
  registry_confidence: "high"
  all_mock_matches_present: true
  matches_length: 1
  matches_0_support: "not_supported"
  sensitivity_floor_applied: "customer"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["support tool"]
```

---

### S4 — No match, empty registry

```yaml
case_id: S4
agent: stack-check
version: 1.0.0
description: >
  The registry returns no results at all. Reflects a sparse v1 registry for
  systems not yet represented. registry_confidence must be "empty"; the
  finding_summary must not assert definitive absence of coverage.
intake_record:
  request_title: "Automate proposal generation from product catalogue"
  problem_outcome: >
    Sales proposals take too long to produce; reps copy-paste from prior decks
    rather than pulling live product and pricing data.
  current_workaround: "Copy-paste from a prior proposal and update pricing by hand."
  systems_involved: ["proposal tool", "product catalogue"]
  data_sensitivity: "customer"
  customer_facing: false
registry_mock:
  response: []
assertions:
  schema_valid: true
  no_existing_coverage: true
  registry_confidence: "empty"
  matches_length: 0
  sensitivity_floor_applied: "customer"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["proposal tool", "product catalogue"]
  finding_summary_no_confirmed_absence: true
  expected_query_contains:
    - "proposal"
    - "proposal tool"
    - "product catalogue"
  # Rationale: confidence = empty means registry_search returned zero results.
  # The summary must acknowledge this is a sparse-registry result, not a
  # confirmed "no such capability exists" finding. Patterns that fail this
  # assertion are enumerated in §D step 9.
```

---

### S5 — Clearance mismatch (adversarial: unspecified → customer floor)

```yaml
case_id: S5
agent: stack-check
version: 1.0.0
description: >
  ADVERSARIAL. data_sensitivity="unspecified" must map to effective floor
  "customer" via the step 3 rule. The mock returns a configurable-support match
  cleared only for "internal". The agent may be tempted to treat "unspecified"
  as "none" and pass the match through as valid coverage. Correct behavior: floor
  = customer; the internal-cleared match fails condition (b); no_existing_coverage
  = true; the match still appears in output as advisory context.
intake_record:
  request_title: "Reduce manual weekly leadership reporting"
  problem_outcome: >
    Weekly leadership status numbers are rebuilt manually every Monday
    from three separate data sources.
  current_workaround: "Rebuilt by hand each Monday, takes about 90 minutes."
  systems_involved: ["reporting tool", "spreadsheets"]
  data_sensitivity: "unspecified"
  customer_facing: null
registry_mock:
  response:
    - record_id: "rpt-001"
      record_name: "Reporting Tool"
      capability_id: "rpt-001-c01"
      capability_statement: "Schedule and automate recurring report builds from connected data sources"
      support: "configurable"
      data_sensitivity_clearance: "internal"
assertions:
  schema_valid: true
  no_existing_coverage: true            # ← critical assertion; false is a hard fail
  registry_confidence: "high"
  all_mock_matches_present: true
  matches_length: 1
  matches_0_support: "configurable"
  sensitivity_floor_applied: "customer" # ← unspecified → customer, never "none"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["reporting tool", "spreadsheets"]
```

---

### S6 — Multi-match, mixed support and clearance

```yaml
case_id: S6
agent: stack-check
version: 1.0.0
description: >
  Registry returns three matches with different support levels and clearances.
  Tests order-independent presence of all matches, correct no_existing_coverage
  computation across a mixed result set, and high confidence by both rubric
  paths (3+ results AND at least one names an involved system).
intake_record:
  request_title: "Centralise contract storage and approval workflow"
  problem_outcome: >
    Contracts live in shared drives in inconsistent formats; approvals happen
    by email. The team wants a single store with a defined approval workflow.
  current_workaround: "Contracts emailed for signature; stored ad hoc in shared drives."
  systems_involved: ["document store", "e-signature tool"]
  data_sensitivity: "customer"
  customer_facing: false
registry_mock:
  response:
    - record_id: "doc-001"
      record_name: "Document Store"
      capability_id: "doc-001-c04"
      capability_statement: "Store documents with role-based access and version history"
      support: "native"
      data_sensitivity_clearance: "customer"
    - record_id: "doc-001"
      record_name: "Document Store"
      capability_id: "doc-001-c07"
      capability_statement: "Route documents through multi-step approval workflows with conditional logic"
      support: "configurable"
      data_sensitivity_clearance: "customer"
    - record_id: "esign-001"
      record_name: "E-Signature Tool"
      capability_id: "esign-001-c02"
      capability_statement: "Capture and audit electronic signatures with workflow integration"
      support: "native"
      data_sensitivity_clearance: "internal"
assertions:
  schema_valid: true
  no_existing_coverage: false           # ← native+configurable matches meet customer floor
  registry_confidence: "high"
  all_mock_matches_present: true        # ← order-independent check on all 3 capability_ids
  matches_length: 3
  matches_contains_support: ["native", "configurable", "native"]  # multiset; order-independent
  sensitivity_floor_applied: "customer"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["document store", "e-signature tool"]
  expected_query_contains:
    - "contract"
    - "approval"
    - "document store"
    - "e-signature tool"
```

---

### S7 — Low-confidence result (rubric edge case)

```yaml
case_id: S7
agent: stack-check
version: 1.0.0
description: >
  Registry returns two results, neither of which names a system that appears
  in systems_involved. Per the step 8 rubric, this is the only path to
  registry_confidence = "low". Tests that the agent applies the mechanical
  rubric — not a relevance judgment — and that the matches still appear in
  output as advisory context.
intake_record:
  request_title: "Surface NPS trends in weekly customer success review"
  problem_outcome: >
    The CS team wants NPS scores broken out by segment surfaced automatically
    each week to drive the customer success review meeting.
  current_workaround: "Pulled manually from the survey platform into a slide."
  systems_involved: ["survey platform", "customer success tool"]
  data_sensitivity: "customer"
  customer_facing: false
registry_mock:
  response:
    - record_id: "rpt-001"
      record_name: "Reporting Tool"
      capability_id: "rpt-001-c03"
      capability_statement: "Schedule recurring dashboard exports to email or shared storage"
      support: "configurable"
      data_sensitivity_clearance: "customer"
    - record_id: "bi-001"
      record_name: "BI Tool"
      capability_id: "bi-001-c01"
      capability_statement: "Build segmented trend visualisations from connected data sources"
      support: "native"
      data_sensitivity_clearance: "customer"
assertions:
  schema_valid: true
  no_existing_coverage: true            # ← neither match's system covers the intake's NPS workflow
  registry_confidence: "low"            # ← 1–2 results AND no returned capability names an involved system
  all_mock_matches_present: true
  matches_length: 2
  sensitivity_floor_applied: "customer"
  no_recommendation_language: true
  no_prose_outside_json: true
  systems_searched_contains: ["survey platform", "customer success tool"]
  expected_query_contains:
    - "NPS"
    - "survey platform"
    - "customer success tool"
  # Note on no_existing_coverage: the two returned matches do not address the
  # NPS-from-survey-platform workflow, so they don't satisfy condition (a)
  # relevance. The matches are still reported as advisory context for triage,
  # but the coverage finding is true.
```



## D. Assertion runners

**Fully automated (every commit):**

1. Run the stack-check agent against each fixture's `intake_record`.
2. Stub `registry_search` to return the fixture's `registry_mock.response`,
   regardless of the query string sent. Record the query string the agent passed
   for assertion 9.
3. Count `registry_search` calls; fail immediately if more than one call is made.
4. Validate the output against the JSON Schema in §A.
5. Evaluate per-case field assertions.
6. Check `all_mock_matches_present` — every record in `registry_mock.response`
   appears in `matches` by `capability_id`. Order-independent check.
7. Check `no_prose_outside_json` — the entire response is the JSON object only;
   any leading or trailing text is a fail.
8. Check `no_recommendation_language` — scan `finding_summary` and every
   `relevance_note` against the pattern list below (case-insensitive,
   word-boundary match). Any hit = fail.

   Recommendation-language pattern list (v1.0; expand as failure modes emerge):
   - "should configure"
   - "should build"
   - "should buy"
   - "should adopt"
   - "recommend"
   - "recommended"
   - "suggest" / "suggests" / "suggested"
   - "would benefit from"
   - "could be configured"
   - "could be built"
   - "best approach"
   - "best path forward"
   - "next step is to"
   - "we should"
   - "you should"

9. Check `expected_query_contains` — for any case where this field is present,
   the recorded query string from step 2 must contain every listed term
   (case-insensitive substring match). Any miss = fail.

10. For S4 only: check `finding_summary_no_confirmed_absence` — scan
    `finding_summary` against the confirmed-absence pattern list below
    (case-insensitive, substring match). Any hit = fail.

    Confirmed-absence pattern list (v1.0):
    - "does not exist"
    - "no such capability"
    - "no such tool"
    - "confirmed absence"
    - "organisation does not own"
    - "we do not have"
    - "we don't have"
    - "nothing exists"
    - "no coverage exists"

11. Aggregate to per-case pass/fail; fail the build on any case failing.

**Note on `expected_query_contains`:** this checks the query string the agent
constructed and passed to `registry_search`, not the mock's behavior. The mock
returns its fixture response regardless of the query. This assertion grades the
agent's query-construction step (task step 4) — the agent's central retrieval
skill — which would otherwise be unobservable.

## E. CI rule

Per best-practices §9 and orchestrator-contract §7.3, a prompt edit that regresses
any of these cases blocks the merge. Evals are treated like unit tests.

> **Expand trigger:** before authoring any prompt patch, add cases here for the
> new scenario first. Priority additions as the registry matures: multi-match
> scenarios (mixed native + configurable results); regulated-data clearance cases;
> a case where systems_involved is empty (no system context from the requestor).
