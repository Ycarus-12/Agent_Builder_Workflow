---
artifact: triage-evals
version: 1.1.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Eval-first scaffold for the triage-recommender agent. Because triage emits structured
  output, the bulk is machine-checkable against a JSON schema plus per-case cross-field
  assertions; layered on top is a judgment rubric (1-5) scored by a judge model, because
  "correct recommended outcome" and "sound cascade reasoning" are not schema-checkable.
  Rewritten for triage v1.1.0, whose output is now TWO things: a costable `options[]`
  short list (1-4, route-typed configure|build|buy) and a single `recommendation` object
  (one of the six outcomes) that points into the list via `recommended_option_id`. The
  bulk of the new machine layer enforces the option/recommendation split, the
  route-specific field coupling on each option, and referential integrity between the
  recommendation and the list. Cases cover all six outcomes once each as the recommended
  outcome before the rollout-step expansion to the full 5-10 per outcome.
covers:
  - triage-recommender v1.1.0
dependencies:
  - Architecture & Process Specification v0.3 §6, §10.4, Appendix B (costable short list)
  - Orchestrator Contract v1.1.0 §5 (validate-and-retry), §6 (sensitivity overlay), §7 (eval harness)
  - cost-estimation-rom v1.1.0 (the consumer of `options[]`; this suite's option schema is ROM's input contract, so a green run here is also a triage->ROM seam check)
  - Prompt-Authoring Best Practices §3 (eval-first), §4 (advisory output), §9 (CI rule)
changelog: >
  v1.1.0 rewritten for triage v1.1.0. Output schema changed from `recommendations[]`
  (1-3, keyed by outcome) to `options[]` (1-4, route-typed) plus a single `recommendation`
  object. Cross-field assertions rewritten: option route-field coupling (tool_name/
  capability_id for configure, avenue/engine/weight for build, vendor_or_category/
  bought_capability for buy); recommended_option_id referential integrity and null-iff
  rules; alternatives integrity; configure provenance/floor on options. Enum vocab aligned
  to the agent contracts (avenue underscored, engine lowercase, weight light|heavy).
  v1.0.0 initial scaffold (recommendations[] contract; superseded).
---

# Triage / recommender Agent: Eval Scaffold (v1.1.0)

Two layers. The **machine-checkable contract** (§C, §D) runs every commit and is the
primary gate. The **judgment rubric** (§A, §B) runs as a judge-model call pre-merge on
prompt changes, because outcome correctness and reasoning quality are not
schema-checkable. A case passes only if it clears both layers.

> **What changed in v1.1.0.** Triage now emits an `options[]` short list (1-4, every
> option route-typed `configure`/`build`/`buy`) AND a single `recommendation` object whose
> `outcome` is one of the six cascade results. For `configure`/`build`/`buy` the
> recommendation points at an option via `recommended_option_id`; for `route_elsewhere`/
> `dont_build`/`process_training_fix` that field is `null` and the list holds the notional
> option(s) that would have been pursued. The option schema below is byte-for-byte what
> cost-estimation-rom v1.1.0 consumes, so a green run here also proves the triage->ROM seam.

## A. Judgment rubric (1-5)

Score each dimension 1-5; **3 is the pass bar.** A case passes only if every dimension
is ≥ 3 and no hard fail (below) fired.

| Dimension | 1 (fail) | 3 (pass) | 5 (excellent) |
|---|---|---|---|
| **Correct recommended outcome** | Picks the wrong cascade resolution | Picks the outcome two reviewers would agree on | As pass, plus the rationale names exactly why this gate and not the cheaper ones |
| **Cheapest-first discipline** | Drifts to `build`/`buy` when a cheaper gate resolved | Stops at the first genuinely resolving gate | As pass, and resists a tempting expensive outcome where a cheaper one truly fits |
| **Cascade-trace integrity** | Trace missing, out of order, or does not stop at the recommended outcome's gate | Ordered, last entry resolves, maps to `recommendation.outcome` | As pass, with crisp gate-by-gate reasoning a reviewer can audit |
| **Costable option list** | Options empty, >4, a non-costable route, or a build option missing avenue/engine/weight | 1-4 options, all route-typed configure/build/buy, every build option fully specified, each named precisely enough to cost | As pass, and the notional option(s) for a non-build recommendation are the genuinely relevant ones |
| **Recommendation wiring** | `recommended_option_id` dangles, points to the wrong route, or is set/null against the rule | Points to a real option whose route matches the outcome for configure/build/buy; null for route_elsewhere/dont_build/process_training_fix | As pass, with the recommended option clearly the right pick among the list |
| **Sensitivity overlay** | Sensitivity changed the route, or `unspecified` treated as `none`, or overlay missing | Recorded; `unspecified` treated as sensitive; route and option list visibly unchanged | As pass, with a precise note on the guardrail it raises (security review, R&D sign-off) |
| **Alternatives justified** | Padded options, or a real fork missed, or an alternative repeats the recommended option | Alternatives genuinely competitive; each `why_secondary` honest; no padding | As pass, and the fork is framed around the single fact it turns on |
| **Stays advisory** | Decides/blocks, estimates cost or time, or invents registry coverage | Recommends only; no numbers; a configure option cited to a real match | As pass, plus an `uncertainty` note that genuinely aids the Gate 1a decision |

**Hard fail (auto-zero regardless of other scores):**
- Emits a `configure` option (or recommends `configure`) without a real stack-check match
  at `native`/`configurable`, or when `registry_confidence` is `"empty"`.
- Changes, promotes, demotes, or re-routes the recommended outcome because of data
  sensitivity.
- Estimates cost, effort, hours, dollars, or feasibility.
- Blocks, rejects, or declines a request as a decision (rather than recommending
  `dont_build` advisorily).
- Cascade trace's resolving gate does not map to `recommendation.outcome`.
- `options` is empty, or any option's `route` is not one of `configure`/`build`/`buy`.

## B. Judgment scenarios

| # | Scenario | What the agent must do |
|---|---|---|
| T1 | Out-of-scope IT/facilities request | Recommend `route_elsewhere` at gate 1; name the team; `recommended_option_id` null; options hold a notional option; trace stops at gate 1 |
| T2 | Trivial one-off ask | Recommend `dont_build`; `recommended_option_id` null; options hold the notional build; trace stops at gate 2 |
| T3 | Clean configurable registry hit | Recommend `configure`; a configure option cites the match; `recommended_option_id` points to it; do not drift to build |
| T4 | Owned native capability, unknown to requestor | Recommend `process_training_fix`; `recommended_option_id` null; **no** configure option (nothing to configure); options hold a notional surfacing build |
| T5 | Commodity capability, no coverage | Recommend `buy`; a buy option, plus an optional light-build alternative with honest `why_secondary` |
| T6 | No coverage, sensitive, judgment task | Recommend `build`; the build option is `avenue=code`, `engine=ai`, `weight=heavy`; overlay `regulated` + R&D sign-off; route unchanged |
| T7 | Marginal fit / low registry confidence | Recommend `configure` with a `build` alternative (`avenue=code`, `engine=deterministic`, `weight=light`); honest `why_secondary`; low confidence in `uncertainty` |
| T8 *(adversarial)* | Sensitive data on an otherwise plain configure | Keep `configure`; raise guardrails in the overlay; do NOT re-route because it is sensitive |
| T9 *(adversarial)* | Empty registry (`registry_confidence: "empty"`) but clearly buildable | No configure option anywhere; do NOT invent a match; recommend `build` |

All six outcomes appear as the recommended outcome at least once (T1 route_elsewhere,
T2 dont_build, T3 configure, T4 process_training_fix, T5 buy, T6 build).

## C. Machine-checkable contract

Output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "TriageOptionListAndRecommendation",
  "type": "object",
  "additionalProperties": false,
  "required": ["request_title", "options", "recommendation", "sensitivity_overlay", "uncertainty", "cascade_trace"],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "options": {
      "type": "array",
      "minItems": 1,
      "maxItems": 4,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["option_id", "route", "label", "summary", "tool_name", "capability_id", "avenue", "engine", "weight", "vendor_or_category", "bought_capability"],
        "properties": {
          "option_id": { "type": "string", "minLength": 1 },
          "route": { "type": "string", "enum": ["configure", "build", "buy"] },
          "label": { "type": "string", "minLength": 1 },
          "summary": { "type": "string", "minLength": 1 },
          "tool_name": { "type": ["string", "null"] },
          "capability_id": { "type": ["string", "null"] },
          "avenue": { "type": ["string", "null"], "enum": ["code", "agent_creation", "config_applied", "config_instructions", null] },
          "engine": { "type": ["string", "null"], "enum": ["ai", "deterministic", null] },
          "weight": { "type": ["string", "null"], "enum": ["light", "heavy", null] },
          "vendor_or_category": { "type": ["string", "null"] },
          "bought_capability": { "type": ["string", "null"] }
        }
      }
    },
    "recommendation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["outcome", "recommended_option_id", "rationale", "risks", "destination_team", "alternatives"],
      "properties": {
        "outcome": { "type": "string", "enum": ["route_elsewhere", "dont_build", "configure", "process_training_fix", "buy", "build"] },
        "recommended_option_id": { "type": ["string", "null"] },
        "rationale": { "type": "string", "minLength": 1 },
        "risks": { "type": "array", "items": { "type": "string" } },
        "destination_team": { "type": ["string", "null"] },
        "alternatives": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["option_id", "why_secondary"],
            "properties": {
              "option_id": { "type": "string", "minLength": 1 },
              "why_secondary": { "type": "string", "minLength": 1 }
            }
          }
        }
      }
    },
    "sensitivity_overlay": {
      "type": "object",
      "additionalProperties": false,
      "required": ["effective_sensitivity", "guardrail_note"],
      "properties": {
        "effective_sensitivity": { "type": "string", "enum": ["none", "internal", "customer", "financial", "regulated", "unspecified"] },
        "guardrail_note": { "type": "string", "minLength": 1 }
      }
    },
    "uncertainty": { "type": "string", "minLength": 1 },
    "cascade_trace": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["gate", "resolved", "reasoning"],
        "properties": {
          "gate": { "type": "string" },
          "resolved": { "type": "boolean" },
          "reasoning": { "type": "string", "minLength": 1 }
        }
      }
    }
  }
}
```

> **Runtime note.** The nullable route-specific leaf fields are `["string","null"]`, and
> `avenue`/`engine`/`weight` carry an enum that includes `null`. If the production
> gateway's constrained-decoding implementation rejects a `null` member inside `enum`, or
> rejects nullable leaves under `additionalProperties:false`, split each option into a
> per-route variant via `oneOf` (one branch per route with only that route's fields
> required and non-null), and re-test. Escalate per best-practices §3b rather than
> loosening `additionalProperties`.

### Beyond schema-validity: cross-field assertions (every case)

Schema-valid is necessary but not sufficient. The harness also asserts, deterministically:

1. **Option list shape.** `options` has 1-4 entries. Every `option_id` is unique within
   the list. Every `route` is one of `configure`/`build`/`buy`.
2. **Option route-field coupling.** Per option, the route-specific fields are non-null
   **iff** the route calls for them, and null otherwise:
   - `tool_name` AND `capability_id` non-null **iff** `route == "configure"`.
   - `avenue` AND `engine` AND `weight` non-null **iff** `route == "build"`.
   - `vendor_or_category` AND `bought_capability` non-null **iff** `route == "buy"`.
3. **Build option fully specified.** For every `route == "build"` option, `avenue` ∈
   {code, agent_creation, config_applied, config_instructions}, `engine` ∈ {ai,
   deterministic}, and `weight` ∈ {light, heavy} — all present (this is what ROM costs on).
4. **Recommendation null-rule + referential integrity.**
   - `recommended_option_id` is `null` **iff** `recommendation.outcome` ∈
     {route_elsewhere, dont_build, process_training_fix}.
   - `recommended_option_id` is non-null **iff** `recommendation.outcome` ∈
     {configure, build, buy}; when non-null it equals exactly one `options[].option_id`,
     and that option's `route` equals the outcome.
5. **Alternatives integrity.** Each `alternatives[].option_id` resolves to an `option_id`
   in `options`, is **not** equal to `recommended_option_id`, and carries a non-empty
   `why_secondary`. (`alternatives` may be `[]`.)
6. **destination_team coupling.** `recommendation.destination_team` is non-null **iff**
   `recommendation.outcome == "route_elsewhere"`.
7. **Configure provenance.** Any `configure` option's `capability_id` references a
   `record_id` + `capability_id` pair present in the case's `stack_check_result.matches`.
   No invented matches.
8. **Configure evidence floor.** No option has `route == "configure"` when the case's
   `stack_check_result.registry_confidence == "empty"` **or** `no_existing_coverage == true`.
9. **Trace integrity.** `cascade_trace` is contiguous from the first gate in cascade
   order; exactly one entry has `resolved == true`; it is the **last** entry; and its
   `gate` maps to `recommendation.outcome` (gate→outcome map below).
10. **Sensitivity floor.** If the intake record's `data_sensitivity == "unspecified"`,
    then `sensitivity_overlay.effective_sensitivity == "unspecified"`, and
    `recommendation.outcome` equals the case's expected outcome (i.e. sensitivity did not
    move the route).
11. **No prose outside JSON.** Response is the JSON object only, no fences or preamble.

**Gate → outcome map** (for assertion 9; the trace `gate` text maps to an outcome):
`Belongs to another function?`→`route_elsewhere`, `Worth solving?`→`dont_build`,
`Does a tool we own fit?`→`configure`, `Process or training gap?`→`process_training_fix`,
`Does buying beat building?`→`buy`, `Otherwise build`→`build`.

> The map keys are the canonical gate labels. The harness normalizes on these strings;
> if the prompt's gate wording drifts, update the map in lockstep (it is an audited
> artifact).

## D. Cases

Each case supplies an `<intake_record>`, `<transcript>`, and `<stack_check_result>`
fixture plus the assertions below. Fixture format mirrors orchestrator-contract §7.1
(one file per case, stored alongside this artifact in the registry repo).

| # | Inputs (sketch) | Key assertions |
|---|---|---|
| T1 | VPN/laptop request; empty/no coverage | outcome `route_elsewhere`; `destination_team` set; `recommended_option_id` null; `options` length ≥1 (notional); trace length 1; overlay does not re-route |
| T2 | one-off folder rename, single person | outcome `dont_build`; `recommended_option_id` null; options hold a notional build; trace stops at `Worth solving?` |
| T3 | lead-routing; one `configurable` match, confidence high | outcome `configure`; a configure option whose `capability_id` traces to the match; `recommended_option_id` points to it (route configure); no build recommended; trace stops at `Does a tool we own fit?` |
| T4 | expense-codes; one `native` match but requestor unaware | outcome `process_training_fix`; `recommended_option_id` null; **no** option has route `configure`; options hold a notional surfacing build; trace walks to gate 4 |
| T5 | e-signature; commodity, no coverage | outcome `buy`; recommended option route `buy`; optional `build` alternative listed in `alternatives` with `why_secondary` |
| T6 | regulated complaint triage; no coverage, confidence high | outcome `build`; recommended build option `avenue=code`, `engine=ai`, `weight=heavy`; overlay `regulated` + R&D sign-off; trace walks all six gates |
| T7 | weekly report; one `configurable` match, confidence **low** | outcome `configure`; `build` alternative (`avenue=code`, `engine=deterministic`, `weight=light`) in `alternatives`; configure option traces to the match; low confidence in `uncertainty` |
| T8 | plain configurable hit but `data_sensitivity=customer` | outcome stays `configure` (not re-routed); overlay raises guardrails; assertion 10 holds |
| T9 | clearly buildable; `registry_confidence="empty"` | **no** configure option (assertions 7-8); outcome `build`; nothing invented |

> **Coverage note.** T4 (`process_training_fix`) and T5 (`buy`) exist specifically so
> every outcome is exercised as the recommended outcome, not merely as a `resolved:false`
> rung. `process_training_fix` is the outcome most easily confused with `configure` and
> `dont_build`, so its dedicated case is load-bearing, not filler. T4 and T9 also guard
> the asymmetry that matters most under the new contract: a non-build/non-configure
> recommendation still produces a costable option list, but it must NOT manufacture a
> `configure` option to do it.

> **CI rule (orchestrator-contract §7.3, best practices §9):** a schema or cross-field
> assertion failure blocks the merge. A rubric median dropping below 3 on any dimension,
> or below the previous baseline by more than 1 point on any dimension, blocks the merge.
> Rubric improvements record a new baseline. Every run logs the prompt version + commit
> hash so regressions trace to the change that introduced them.
