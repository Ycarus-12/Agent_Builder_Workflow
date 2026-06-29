---
artifact: cost-estimation-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Combined eval scaffold for the cost-estimation agent's two modes. Covers
  cost-estimation-rom v1.1.0 (mechanical, machine-checkable) and
  cost-estimation-deepdive v1.0.0 (judgment-bearing, hybrid machine-checkable
  plus rubric scoring). Same one-file pattern used by intake-evals (which
  covers conversation + extraction).
covers:
  - cost-estimation-rom v1.1.0
  - cost-estimation-deepdive v1.0.0
dependencies:
  - Prompt-Authoring Best Practices §3 (eval-first), §6 (orchestrator contract),
    §8 (rollout)
  - orchestrator-contract v1.1.0 §7 (eval harness shape)
  - Architecture & Process Specification v0.3 §7 (Cost Estimation), §10.5
    (Cost agent)
changelog: v1.0.0 initial scaffold.
---

# Cost-Estimation Agent: Eval Scaffold (v1.0.0)

This scaffold covers both modes of the cost-estimation agent. ROM mode is
fully machine-checkable (mechanical rubric → deterministic output). Deep-dive
mode is hybrid: schema and field rules are machine-checkable; phase
decomposition quality, recommendation quality, and source-citation
correctness are scored by rubric.

The harness runs ROM cases on every commit (fast, deterministic). Deep-dive
cases run on a schedule and on every PR touching the deep-dive prompt
(slower; web tools involved).

---

## PART A — ROM mode (cost-estimation-rom v1.1.0)

### A.1 Machine-checkable contract

The ROM output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CostEstimationROM",
  "type": "object",
  "additionalProperties": false,
  "required": ["request_title", "costed_options", "estimate_summary"],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "costed_options": {
      "type": "array",
      "minItems": 1,
      "maxItems": 4,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "option_id", "route", "label", "effort_band", "run_cost_band",
          "license_band", "maintenance_band", "confidence", "key_drivers"
        ],
        "properties": {
          "option_id":    { "type": "string", "minLength": 1 },
          "route":        { "type": "string", "enum": ["configure", "build", "buy"] },
          "label":        { "type": "string", "minLength": 1 },
          "effort_band":  { "type": "string", "enum": ["XS", "S", "M", "L", "XL"] },
          "run_cost_band": {
            "type": ["string", "null"],
            "enum": ["negligible", "low", "moderate", "high", null]
          },
          "license_band": {
            "type": ["string", "null"],
            "enum": ["none", "low", "mid", "high", "unknown", null]
          },
          "maintenance_band": {
            "type": "string",
            "enum": ["negligible", "low", "medium", "high"]
          },
          "confidence":   { "type": "string", "enum": ["high", "medium", "low"] },
          "key_drivers": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": { "type": "string", "minLength": 1 }
          }
        },
        "allOf": [
          {
            "if": { "properties": { "route": { "const": "configure" } } },
            "then": {
              "properties": {
                "run_cost_band": { "const": null },
                "license_band":  { "const": null }
              }
            }
          },
          {
            "if": { "properties": { "route": { "const": "build" } } },
            "then": {
              "properties": {
                "license_band":  { "const": null }
              }
            }
          },
          {
            "if": { "properties": { "route": { "const": "buy" } } },
            "then": {
              "properties": {
                "license_band": {
                  "type": "string",
                  "enum": ["none", "low", "mid", "high", "unknown"]
                }
              }
            }
          }
        ]
      }
    },
    "estimate_summary": { "type": "string", "minLength": 1, "maxLength": 800 }
  }
}
```

### A.2 Per-case assertions

Each ROM fixture asserts:

- `schema_valid: true`
- `option_count_matches_input: true` — costed_options length equals input option list length
- `option_order_preserved: true` — costed_options[i].option_id == input.options[i].option_id for all i
- `field_assertions:` per-case expected values (band, confidence, route, etc.)
- `key_drivers_count_in_range: true` — every option's key_drivers has 2 or 3 entries
- `no_prose_outside_json: true` — response is the JSON object only
- `no_dollar_figures: true` — output contains no "$", "USD", "dollar", or numeric currency patterns
- `no_timeline_language: true` — output contains no "week", "day", "month" used as duration, no calendar dates
- `no_cross_option_recommendation: true` — estimate_summary describes cost shape only; does not say which option to pick

### A.3 Scoring rubric (1–5)

Hybrid: most ROM behavior is machine-checked above. The rubric covers
behaviors that don't reduce cleanly to deterministic assertions.

| Dimension | What to look for |
|---|---|
| **Band plausibility** | Per-option bands fall within one neighbor of a reasonable expert estimate for the same option and intake. |
| **Confidence calibration** | High confidence only when intake is genuinely rich and option fully specified. Low confidence used when intake is sparse or option fields are thin. |
| **Key driver identification** | Drivers cite specific signals from the extract or option (e.g., "systems_count=3", "engine=ai raises maintenance"), not generic descriptions. |
| **Sensitivity modifier correctness** | Build effort lifted appropriately when data_sensitivity is customer/financial/regulated/unspecified. Not applied to configure or buy. |
| **Schema discipline** | configure has null run_cost_band and null license_band; build has null license_band; build with engine=deterministic has null run_cost_band; buy has a non-null license_band. |
| **Output cleanliness** | No prose contamination, no preamble, no dollar figures, no timeline language, no cross-option recommendation. |

Score interpretation:
- **5** — Exemplary; would not be improved by an expert rewrite.
- **4** — Solid; minor polish only.
- **3** — Acceptable; one or two dimensions are weak but the output is usable.
- **2** — Material issues; output should be re-run or escalated.
- **1** — Output is wrong or unsafe; merge blocked.

### A.4 ROM test cases (R1–R6)

Each case is one fixture file (YAML) with: `intake_record`, `option_list`,
and `expected` assertions.

**R1 — Clear configure match, low complexity**

- Intake: rich; CRM → work-management trigger; data_sensitivity=customer.
- Option list: one configure option naming a registered native capability.
- Expected: effort_band=S; run_cost_band=null; license_band=null;
  maintenance_band=low; confidence=high; key_drivers cite the named
  capability and the bounded scope.

**R2 — Light deterministic build, no AI**

- Intake: clear; one acceptance criterion describes a webhook handler; one
  system; no scope edge cases; data_sensitivity=internal.
- Option list: one build option with avenue=code, engine=deterministic,
  weight=light.
- Expected: effort_band=S (rubric base S, no sensitivity raise);
  run_cost_band=null; license_band=null; maintenance_band=low;
  confidence=high.

**R3 — AI build, heavy, customer data**

- Intake: customer-facing ticket assistance; data_sensitivity=customer;
  multiple integrations described.
- Option list: one build option with avenue=agent_creation, engine=ai,
  weight=heavy.
- Expected: effort_band=L (rubric base L for heavy AI; XL only if
  integration_signals confirmed and systems_count >= 2; band reflects
  sensitivity raise); run_cost_band=moderate or high;
  license_band=null; maintenance_band=high; confidence=medium.

**R4 — Sparse intake, three-option list**

- Intake: one acceptance criterion, no solution_idea, no current_workaround,
  one system; data_sensitivity=customer.
- Option list: one configure, one build (AI, light), one buy.
- Expected: every option's confidence=low; key_drivers explicitly name the
  missing signals (sparse acceptance criteria, no solution_idea, etc.);
  bands are defensible but the summary flags that tightening the intake
  would lift confidence.

**R5 — Clear buy signal, four-option list**

- Intake: requests a generic capability with broad market coverage (e.g.,
  proposal generation); solution_idea names a known vendor category;
  systems_involved includes the vendor.
- Option list: configure (existing tool stretch), build (AI, light), buy
  (named mid-market vendor), buy (alternate vendor category).
- Expected: both buy options have non-null license_band; buy effort_band
  reflects integration only (XS or S, not L); build option band stands
  cleanly; configure option's key_drivers note the stretch-fit.

**R6 — Adversarial requestor undersell**

- Intake: requestor's effort_estimate says "just a quick script"; problem
  description has rich complexity signals (multiple systems, scope edges,
  customer-facing); acceptance criteria detailed.
- Option list: one build option with avenue=code, engine=deterministic,
  weight=light.
- Expected: effort_band L or M (NOT XS or S); the agent does not defer to
  the requestor's framing; key_drivers cite the complexity signals
  overriding the requestor's estimate; confidence=medium (the gap between
  requestor framing and actual signals creates an explicit risk).

---

## PART B — Deep-dive mode (cost-estimation-deepdive v1.0.0)

### B.1 Machine-checkable contract

The deep-dive output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CostEstimationDeepDive",
  "type": "object",
  "additionalProperties": false,
  "required": ["request_title", "directions", "recommendation"],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "directions": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "option_id", "route", "label", "phases", "effort_total",
          "run_cost", "license_cost", "maintenance",
          "first_year_total_usd", "annual_steady_state_usd",
          "assumptions", "risks"
        ],
        "properties": {
          "option_id":    { "type": "string", "minLength": 1 },
          "route":        { "type": "string", "enum": ["configure", "build", "buy"] },
          "label":        { "type": "string", "minLength": 1 },
          "phases": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["name", "effort_low_h", "effort_expected_h", "effort_high_h", "notes"],
              "properties": {
                "name":              { "type": "string", "minLength": 1 },
                "effort_low_h":      { "type": "number", "minimum": 0 },
                "effort_expected_h": { "type": "number", "minimum": 0 },
                "effort_high_h":     { "type": "number", "minimum": 0 },
                "notes":             { "type": ["string", "null"] }
              }
            }
          },
          "effort_total": {
            "type": "object",
            "additionalProperties": false,
            "required": ["low_h", "expected_h", "high_h"],
            "properties": {
              "low_h":      { "type": "number", "minimum": 0 },
              "expected_h": { "type": "number", "minimum": 0 },
              "high_h":     { "type": "number", "minimum": 0 }
            }
          },
          "run_cost": {
            "oneOf": [
              { "type": "null" },
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["monthly_low_usd", "monthly_expected_usd", "monthly_high_usd", "basis", "sources"],
                "properties": {
                  "monthly_low_usd":      { "type": "number", "minimum": 0 },
                  "monthly_expected_usd": { "type": "number", "minimum": 0 },
                  "monthly_high_usd":     { "type": "number", "minimum": 0 },
                  "basis":                { "type": "string", "minLength": 1 },
                  "sources": {
                    "type": "array",
                    "minItems": 1,
                    "items": { "$ref": "#/$defs/source" }
                  }
                }
              }
            ]
          },
          "license_cost": {
            "oneOf": [
              { "type": "null" },
              {
                "type": "object",
                "additionalProperties": false,
                "required": ["annual_usd", "basis", "sources"],
                "properties": {
                  "annual_usd": { "type": "number", "minimum": 0 },
                  "basis":      { "type": "string", "minLength": 1 },
                  "sources": {
                    "type": "array",
                    "minItems": 1,
                    "items": { "$ref": "#/$defs/source" }
                  }
                }
              }
            ]
          },
          "maintenance": {
            "type": "object",
            "additionalProperties": false,
            "required": ["monthly_h", "rationale"],
            "properties": {
              "monthly_h": { "type": "number", "minimum": 0 },
              "rationale": { "type": "string", "minLength": 1 }
            }
          },
          "first_year_total_usd": { "$ref": "#/$defs/usd_range" },
          "annual_steady_state_usd": { "$ref": "#/$defs/usd_range" },
          "assumptions": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "string", "minLength": 1 }
          },
          "risks": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "string", "minLength": 1 }
          }
        }
      }
    },
    "recommendation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["recommended_direction", "rationale", "key_tradeoffs", "what_would_change_it"],
      "properties": {
        "recommended_direction": { "type": "string", "minLength": 1 },
        "rationale":             { "type": "string", "minLength": 1 },
        "key_tradeoffs": {
          "type": "array",
          "minItems": 2,
          "maxItems": 4,
          "items": { "type": "string", "minLength": 1 }
        },
        "what_would_change_it":  { "type": "string", "minLength": 1 }
      }
    }
  },
  "$defs": {
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["url", "retrieved_at", "vendor_or_publisher", "note"],
      "properties": {
        "url":                 { "type": "string", "format": "uri" },
        "retrieved_at":        { "type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
        "vendor_or_publisher": { "type": "string", "minLength": 1 },
        "note":                { "type": ["string", "null"] }
      }
    },
    "usd_range": {
      "type": "object",
      "additionalProperties": false,
      "required": ["low", "expected", "high", "basis"],
      "properties": {
        "low":      { "type": ["number", "null"] },
        "expected": { "type": ["number", "null"] },
        "high":     { "type": ["number", "null"] },
        "basis":    { "type": "string", "minLength": 1 }
      }
    }
  }
}
```

### B.2 Per-case assertions

Each deep-dive fixture asserts:

- `schema_valid: true`
- `direction_count_matches_input: true`
- `direction_order_preserved: true` — directions[i].option_id == selected_options[i].option_id for all i
- `recommendation_present: true` — recommendation block is non-null regardless of N
- `recommendation_direction_in_selected: true` — recommendation.recommended_direction matches an option_id in selected_options
- `every_dollar_has_source_or_assumption: true` — every numeric USD field that is non-null has either a sources[] entry OR an explicit assumption in the assumptions array that names the figure
- `retrieved_at_iso_dates: true` — every retrieved_at is YYYY-MM-DD
- `effort_low_le_expected_le_high: true` — within each phase and in effort_total
- `usd_low_le_expected_le_high: true` — within run_cost (when non-null), first_year_total, and steady_state
- `no_prose_outside_json: true`

### B.3 Scoring rubric (1–5)

Deep-dive output is graded on these dimensions. The rubric is a judge-model
call (per orchestrator-contract §7.2) — three runs per case, median scored.

| Dimension | What to look for |
|---|---|
| **Phase decomposition quality** | Phases fit the route and avenue; skip phases that don't apply; phase names are specific (not generic placeholders); the breakdown is plausibly what a domain expert would produce. |
| **Effort range honesty** | low/expected/high spreads reflect real per-phase uncertainty; wide spreads carry a phase note explaining the uncertainty; the expected value is not a midpoint of low and high. |
| **Pricing accuracy** | Cited figures match the cited source (verified by spot-check); sources are current (retrieved_at within the eval run's window); category placeholders are clearly flagged as assumptions. |
| **Maintenance estimation** | The monthly hours figure has a specific rationale (model versioning, integration breakage, vendor management, etc.) — not a generic boilerplate. |
| **Assumption explicitness** | Every material assumption that affects the estimate appears in the assumptions array. No silent assumptions. Category-norm placeholders are flagged. |
| **Risk identification** | Risks are option-specific, not generic ("integration could fail" is generic; "the CRM event payload may lack the owner field needed for AC#3" is specific). Risks identify the band-shifting conditions. |
| **Recommendation calibration to N** | Always emitted. When N > 1: rationale names the load-bearing comparison; key_tradeoffs are specific to the alternatives; what_would_change_it identifies concrete shift conditions, not platitudes. When N == 1: rationale sets expectations (effort and dollar commitment, load-bearing assumption, success picture) rather than re-recommending the choice; key_tradeoffs name the alternatives the Director did NOT pick at Gate 1a (referenced by name from rom_output) plus the implicit cost of the chosen path; what_would_change_it identifies the failure modes that warrant a Gate 1a reconsideration. |
| **ROM band alignment** | When the deep-dive estimate lands materially outside the ROM band, the divergence is explicitly surfaced in assumptions or risks with reasoning. (Anti-pattern: silent disagreement with ROM.) |
| **Output cleanliness** | Schema-valid, citations complete, no prose contamination, no invented prices. |

Score interpretation matches Part A.3.

### B.4 Deep-dive test cases (D1–D5)

Each case is one fixture file with: `intake_extract`, `transcript`,
`stack_check_finding`, `rom_output`, `selected_options`, and `expected`
assertions.

**D1 — N=1 configure direction**

- Selected_options: one configure option for a CRM → work-management
  trigger.
- Expected: phases fit a configure pattern (discovery, configuration,
  integration testing, rollout); recommendation block is populated with
  expectation-setting content (rationale describes the commitment in
  hours and dollars, identifies the load-bearing assumption, and pictures
  success at Gate 2); key_tradeoffs name the build alternative from
  rom_output and the implicit dependency on the host tool's CRM
  integration; what_would_change_it identifies the latency failure mode
  that warrants a Gate 1a reconsideration; run_cost=null;
  license_cost=null; assumptions name the AC#1 latency assumption; risks
  include the latency failure mode.

**D2 — N=1 AI build direction**

- Selected_options: one build option, agent_creation, ai, light, customer
  data.
- Expected: phases include eval setup; run_cost non-null with sources
  citing model pricing; maintenance rationale references model versioning
  and prompt drift; assumptions include token-volume basis; risks include
  prompt drift and customer-data handling; recommendation block populated
  with expectation-setting content (rationale captures the AI run-cost
  commitment and the maintenance burden picture; key_tradeoffs name the
  configure and buy alternatives from rom_output that were not picked).

**D3 — N=2 build vs. buy comparison**

- Selected_options: a light build option and a vendor buy option for the
  same capability.
- Expected: both fully estimated; recommendation block emitted;
  recommended_direction is one of the two option_ids; rationale names a
  specific comparison (cost, risk, time-to-value); key_tradeoffs are
  specific; what_would_change_it identifies a concrete pilot or
  measurement that would shift the choice.

**D4 — N=3 configure / build / buy**

- Selected_options: one of each route.
- Expected: all three estimated; recommendation block emitted naming the
  winner and (in rationale) acknowledging the runner-up; key_tradeoffs
  cover all three options.

**D5 — Pricing unavailable for a buy candidate**

- Selected_options: includes a buy option where the vendor's pricing is
  gated behind sales contact (not publicly available).
- Expected: the buy option's license_cost is either null (with the
  null-rationale stated in assumptions) OR populated with a
  category-norm placeholder explicitly flagged as such in assumptions
  AND noted in risks; no invented vendor-specific number; sources do not
  fabricate a URL.

---

## PART C — CI rules

Inherited from orchestrator-contract v1.1.0 §7.3 with cost-estimation-specific
gates:

- **Any ROM case fails (schema or assertion)** → merge blocked.
- **Any deep-dive case fails the schema** → merge blocked.
- **Deep-dive case fails the `every_dollar_has_source_or_assumption` assertion** → merge blocked. (Hard rule: every dollar figure is traceable.)
- **Deep-dive rubric median drops below 3 on any dimension, or below the previous baseline by more than 1 point on any dimension** → merge blocked.
- **Rubric improves** → new baseline recorded.

The harness records the prompt version + commit hash on every run so
regressions are traceable to the change that introduced them.

---

## D. Metadata footer

- **Artifact:** `cost-estimation-evals`
- **Version:** `1.0.0` · **Owner:** Director · **Status:** Draft
- **Type:** Eval scaffold (not a prompt)
- **Covers:** `cost-estimation-rom` v1.1.0, `cost-estimation-deepdive` v1.0.0
- **Changelog:** `v1.0.0` initial scaffold combining ROM (machine-checkable) and deep-dive (hybrid machine-checkable + rubric) into one file. Finalization pass (2026-06-29): baseline citations aligned to Architecture v0.3 / orchestrator-contract v1.1.0; build-avenue/engine vocabulary normalized (underscored avenue, lowercase engine, non-canonical instructions-only value dropped) to match the agent contracts.
