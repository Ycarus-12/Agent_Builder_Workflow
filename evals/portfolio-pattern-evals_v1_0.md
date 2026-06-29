---
artifact: portfolio-pattern-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Eval-first scaffold for the portfolio-pattern agent. Because the agent emits
  structured output, the bulk is machine-checkable against a JSON schema plus per-case
  cross-field assertions; layered on top is a judgment rubric (1-5) scored by a judge
  model, because "correct signal type," "genuine vs superficial coverage," and "sound
  graduation call" are not schema-checkable. This is the pilot scaffold; cases exercise
  each signal type, each surfaced tier, noise-floor suppression, and both graduation
  outcomes once each before the rollout-step expansion.
covers:
  - portfolio-pattern v1.0.0
dependencies:
  - Architecture & Process Specification v0.3 §10.10, §13 (thresholds, graduation, route-elsewhere recurrence)
  - Orchestrator Contract v1.1.0 §5 (validate-and-retry), §7 (eval harness)
  - Prompt-Authoring Best Practices §3 (eval-first), §4 (advisory output), §9 (CI rule)
changelog: v1.0.0 initial scaffold.
---

# Portfolio / pattern Agent: Eval Scaffold (v1.0.0)

Two layers. The **machine-checkable contract** (§C, §D) runs every commit and is the
primary gate. The **judgment rubric** (§A, §B) runs as a judge-model call pre-merge on
prompt changes, because signal-type correctness, coverage judgment, and graduation calls
are not schema-checkable. A case passes only if it clears both layers.

## A. Judgment rubric (1-5)

Score each dimension 1-5; **3 is the pass bar.** A case passes only if every dimension
is ≥ 3 and no hard fail (below) fired.

| Dimension | 1 (fail) | 3 (pass) | 5 (excellent) |
|---|---|---|---|
| **Correct tier** | Tier does not match the supplied count under the table | Every surfaced theme's tier matches the count→table mapping | As pass, and ordering is strictly most-urgent first |
| **Noise-floor suppression** | Itemizes a count-1-2 cluster, or omits it from `noise_floor_count` | Sub-threshold clusters are counted only, never itemized | As pass, with no padding anywhere in the digest |
| **Signal-type correctness** | Calls a covered theme `build`, or an uncovered theme `enablement`, or misses a route-elsewhere recurrence | Each `signal_type` matches the genuine coverage situation | As pass, and the rationale makes the count-flips-on-coverage logic explicit |
| **Coverage judgment** | Treats keyword overlap as coverage, or ignores genuine coverage | Coverage cited only when a candidate genuinely resolves the theme | As pass, and a near-miss candidate is correctly rejected with a stated reason |
| **Enablement provenance** | Cites a `registry_coverage` record not in the case's `candidate_coverage`, or invents one | `registry_coverage` set iff enablement, and traces to a supplied candidate | As pass, with the cited capability statement the one that actually fits |
| **Graduation grounded in usage** | Graduates on theme volume, or on sporadic usage; or misses an obvious graduate | Flag rests on the supplied usage evidence, not on cluster size | As pass, with the usage threshold reasoning crisp and auditable |
| **Stays advisory** | Decides, gates, routes, commissions a rebuild, or recomputes a count | Surfaces and recommends only; counts echoed; nothing acts | As pass, plus `uncertainty` notes that genuinely aid the Director's read |

**Hard fail (auto-zero regardless of other scores):**
- Itemizes a cluster whose supplied `request_count` is 1 or 2.
- Emits a `tier` that does not match the supplied count under the published table.
- Sets `signal_type == "enablement"` without a genuinely-fitting candidate in the case's
  `candidate_coverage`, or invents a `registry_coverage` record not supplied.
- Sets `signal_type == "build"` when a supplied candidate genuinely resolves the theme.
- Emits a `request_count` that differs from the supplied count (recomputed/adjusted).
- Recommends `graduate` on theme volume alone with no supporting usage evidence.
- Decides, gates, routes, or commissions a rebuild rather than recommending advisorily.

## B. Judgment scenarios

| # | Scenario | What the agent must do |
|---|---|---|
| P1 | Uncovered theme, count 8 | Surface `likely_candidate`, `signal_type=build`, `registry_coverage=null` |
| P2 | Theme natively covered by an owned tool, count 6 | Surface `likely_candidate`, `signal_type=enablement`, cite the record; recommend adoption not build |
| P3 | Recurring out-of-scope (IT/HR) cluster, count 11 | Surface `desperate_need`, `signal_type=route_elsewhere_recurrence`; note the pre-intake-filter signal; coverage null |
| P4 | Three clusters all at count 1-2 | Itemize nothing; `themes=[]`; `noise_floor_count=3` |
| P5 | Pseudo-agent with sustained multi-person usage | `pseudo_agent_graduations` includes `graduate` with usage evidence |
| P6 | Pseudo-agent with sporadic single-user usage | `not_yet`, grounded in the thin usage, not on any theme volume |
| P7 *(adversarial)* | Candidate coverage present but only a superficial keyword overlap, count 7 | Reject the candidate; `signal_type=build`, not `enablement`; state why the candidate does not fit |
| P8 *(adversarial)* | Count-3 theme (bottom of `worth_review`) covered by an owned tool | Surface (not suppress) at `worth_review`; `signal_type=enablement`; do not drop it as "low" |
| P9 *(adversarial)* | A genuinely-covered theme whose count is high (10+) | `desperate_need` tier by count, but still `signal_type=enablement` - tier and signal are independent axes |

Each signal type appears at least once (P1 build, P2 enablement, P3 route_elsewhere_recurrence);
each surfaced tier appears (P8 worth_review, P1/P2 likely_candidate, P3/P9 desperate_need);
both graduation outcomes appear (P5 graduate, P6 not_yet); suppression is exercised (P4).

## C. Machine-checkable contract

Output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PortfolioDigest",
  "type": "object",
  "additionalProperties": false,
  "required": ["digest_date", "themes", "pseudo_agent_graduations", "noise_floor_count"],
  "properties": {
    "digest_date": { "type": "string", "minLength": 1 },
    "themes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["cluster_id", "theme_label", "request_count", "tier", "signal_type", "registry_coverage", "recommendation", "rationale", "risks", "uncertainty", "member_request_ids"],
        "properties": {
          "cluster_id": { "type": "string", "minLength": 1 },
          "theme_label": { "type": "string", "minLength": 1 },
          "request_count": { "type": "integer", "minimum": 3 },
          "tier": { "type": "string", "enum": ["worth_review", "likely_candidate", "desperate_need"] },
          "signal_type": { "type": "string", "enum": ["build", "enablement", "route_elsewhere_recurrence"] },
          "registry_coverage": {
            "type": ["object", "null"],
            "additionalProperties": false,
            "required": ["record_id", "record_name", "capability_statement"],
            "properties": {
              "record_id": { "type": "string" },
              "record_name": { "type": "string" },
              "capability_statement": { "type": "string" }
            }
          },
          "recommendation": { "type": "string", "minLength": 1 },
          "rationale": { "type": "string", "minLength": 1 },
          "risks": { "type": "array", "items": { "type": "string" } },
          "uncertainty": { "type": "string", "minLength": 1 },
          "member_request_ids": { "type": "array", "items": { "type": "string" }, "minItems": 1 }
        }
      }
    },
    "pseudo_agent_graduations": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["record_id", "record_name", "recommendation", "rationale", "usage_evidence"],
        "properties": {
          "record_id": { "type": "string" },
          "record_name": { "type": "string" },
          "recommendation": { "type": "string", "enum": ["graduate", "not_yet"] },
          "rationale": { "type": "string", "minLength": 1 },
          "usage_evidence": { "type": "string", "minLength": 1 }
        }
      }
    },
    "noise_floor_count": { "type": "integer", "minimum": 0 }
  }
}
```

> **Runtime note.** The nullable nested object `registry_coverage` is `["object","null"]`
> with internal `required`. If the production gateway's constrained-decoding
> implementation rejects nullable objects with internal `required`, flatten it to an
> always-present object with nullable leaf fields, or split into sibling scalar fields,
> and re-test. Escalate per best-practices §3b rather than loosening
> `additionalProperties`. The schema's `request_count` minimum of 3 enforces noise-floor
> suppression at the type level: a sub-threshold cluster cannot legally appear as a theme.

### Beyond schema-validity: cross-field assertions (every case)

Schema-valid is necessary but not sufficient. The harness also asserts, deterministically,
given each case's supplied clusters as ground truth:

1. **Tier correctness.** For every theme, `tier` equals the table mapping of the supplied
   `request_count`: 3-5 → `worth_review`, 6-9 → `likely_candidate`, 10+ → `desperate_need`.
2. **Count fidelity.** Every theme's `request_count` equals the supplied count for its
   `cluster_id`. No recomputed or adjusted counts.
3. **Noise-floor suppression.** No theme has a `cluster_id` whose supplied count is 1-2.
   `noise_floor_count` equals the number of supplied clusters with count 1-2.
4. **Surfacing completeness.** Every supplied cluster with count >= 3 appears exactly once
   in `themes`; every cluster with count 1-2 appears in none.
5. **Coverage coupling.** `registry_coverage` is non-null **iff** `signal_type ==
   "enablement"`. It is null for `build` and `route_elsewhere_recurrence`.
6. **Coverage provenance.** Any non-null `registry_coverage.record_id` exists in that
   cluster's supplied `candidate_coverage`. No invented records.
7. **Ordering.** `themes` is ordered by tier urgency: all `desperate_need` before any
   `likely_candidate`, all `likely_candidate` before any `worth_review`.
8. **Member traceability.** Every `member_request_ids` entry is a `request_id` present in
   that cluster's supplied `members`.
9. **Graduation enum + grounding.** Every `pseudo_agent_graduations.record_id` exists in
   the supplied `pseudo_agent_usage`; `recommendation` is one of the two enum values.
10. **No prose outside JSON.** Response is the JSON object only, no fences or preamble.

## D. Cases

Each case supplies a `<clusters>` and `<pseudo_agent_usage>` fixture (with the supplied
counts and candidate coverage as ground truth) plus the assertions below. Fixture format
mirrors orchestrator-contract §7.1 (one file per case, stored alongside this artifact in
the registry repo).

| # | Inputs (sketch) | Key assertions |
|---|---|---|
| P1 | one uncovered cluster, count 8 | tier `likely_candidate`; `signal_type=build`; coverage null; surfaced once |
| P2 | one cluster count 6, one native owned-tool candidate that fits | tier `likely_candidate`; `signal_type=enablement`; coverage traces to the candidate (assertion 6) |
| P3 | one cluster count 11 of out-of-scope IT asks | tier `desperate_need`; `signal_type=route_elsewhere_recurrence`; coverage null |
| P4 | three clusters, counts 2/1/2 | `themes=[]`; `noise_floor_count=3` (assertions 3, 4) |
| P5 | usage: pseudo-agent, sustained multi-person | graduation `graduate` present, traces to the supplied usage (assertion 9) |
| P6 | usage: pseudo-agent, sporadic single-user | graduation `not_yet`; not graduated on volume |
| P7 | cluster count 7, candidate present but only keyword-overlapping | `signal_type=build` (not enablement); coverage null; candidate rejected with a reason |
| P8 | cluster count 3, fitting owned-tool candidate | surfaced at `worth_review` (not suppressed); `signal_type=enablement` |
| P9 | cluster count 12, fitting owned-tool candidate | tier `desperate_need` AND `signal_type=enablement` (tier and signal independent) |

> **Coverage note.** P7 (superficial-overlap rejection) and P9 (high-count enablement)
> are the load-bearing adversarial cases: P7 guards the genuine-coverage judgment that
> separates a build signal from an enablement signal, and P9 guards the independence of
> tier (count-driven) from signal (coverage-driven), the single most likely conceptual
> error in this agent. P8 guards against silently dropping bottom-of-band themes.

> **CI rule (orchestrator-contract §7.3, best practices §9):** a schema or cross-field
> assertion failure blocks the merge. A rubric median dropping below 3 on any dimension,
> or below the previous baseline by more than 1 point on any dimension, blocks the merge.
> Rubric improvements record a new baseline. Every run logs the prompt version + commit
> hash so regressions trace to the change that introduced them.
