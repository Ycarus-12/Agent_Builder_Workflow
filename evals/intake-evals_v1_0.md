---
artifact: intake-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-25
purpose: >
  Light, eval-first scaffold for the intake agent (both halves). Conversation half is
  scored on a 1–5 rubric across representative scenarios; extraction half is graded
  machine-checkably against the JSON schema. This is the pilot scaffold; expand to the
  full 5–10 cases per half at the rollout step.
covers:
  - intake-conversation v1.0.0
  - intake-extraction v1.0.0
dependencies:
  - Prompt-Authoring Best Practices §3 (eval-first), §6 (orchestrator contract), §8 (rollout)
changelog: v1.0.0 initial scaffold.
---

# Intake Agent: Eval Scaffold (v1.0.0)

## A. Conversation half: rubric (1–5)

Score each dimension 1–5; **3 is the pass bar**. A conversation passes only if every
dimension is ≥ 3 and the sign-off dimension is exactly handled.

| Dimension | 1 (fail) | 3 (pass) | 5 (excellent) |
|---|---|---|---|
| **Problem vs. tool** | Accepts the requestor's tool at face value; never surfaces the underlying problem | Captures the problem behind the request | Reframes cleanly, gets the problem concrete, and the tool sits as a non-binding note |
| **Reframing solution-talk** | Lets solution-talk drive; designs the tool with the requestor | Acknowledges the idea, steers back to the problem at least once | Redirects naturally every time, without making the requestor feel dismissed |
| **Workaround depth** | Workaround skipped or one vague line | Workaround captured | Workaround concrete enough to signal possible existing coverage |
| **Routing-critical fields** | Data sensitivity and/or customer-facing left unestablished or assumed | Both explicitly asked and captured | Both established crisply, input vs. output distinguished where relevant |
| **Acceptance criteria** | None, or untestable / vague | Concrete, testable AC drafted and shown | AC a reviewer could verify a build against, phrased positively |
| **Sign-off discipline** | Marker emitted without explicit confirmation, or never reached after confirmation | Marker emitted only after explicit confirmation, on its own final line | As pass, plus a clean recap and correction loop before confirmation |
| **Stays in lane** | Decides, blocks, judges worth, estimates cost/feasibility, or promises a timeline | Captures only; defers all of the above downstream | As pass, plus captures out-of-scope-looking requests neutrally, without judging scope or routing |

**Hard fail (auto-zero regardless of other scores):** emits `[[INTAKE_SIGNOFF_CONFIRMED]]`
without explicit requestor confirmation; rejects or blocks a request; promises a build,
cost, or date; or judges a request out of scope or routes it to another team (a
downstream triage outcome, not intake's call).

## B. Conversation half: scenarios

| # | Scenario | What the agent must do |
|---|---|---|
| C1 | Requestor opens with a named tool ("build me a Zapier zap") | Reframe to the problem; record the tool as non-binding; capture frequency/time/who |
| C2 | Vague request ("reporting is a mess") | Probe to a concrete problem, output, audience, frequency |
| C3 | Requestor never volunteers sensitivity or customer-facing | Explicitly elicit both before recap; neither left unspecified at sign-off |
| C4 | Full happy path | Capture → draft AC → recap → correction → confirm → emit marker once |
| C5 | Looks out of scope ("fix my VPN") | Capture neutrally (problem, frequency, workaround); do NOT judge scope, route to a team, or troubleshoot. Out-of-scope routing is a downstream triage outcome |
| C6 *(stretch)* | Requestor presses "can you build this, how long, how much?" | Defer to post-intake analysis; keep capturing; promise nothing |

## C. Extraction half: machine-checkable contract

The extraction output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "IntakeRecord",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "requestor", "team", "date", "request_title", "problem_outcome",
    "current_workaround", "success_criteria", "frequency", "who_is_affected",
    "time_cost", "deadline", "systems_involved", "data_sensitivity",
    "customer_facing", "solution_idea", "attachments",
    "context_constraints_nuance", "acceptance_criteria", "transcript_reference"
  ],
  "properties": {
    "requestor":                 { "type": ["string", "null"] },
    "team":                      { "type": ["string", "null"] },
    "date":                      { "type": ["string", "null"] },
    "request_title":             { "type": "string", "minLength": 1 },
    "problem_outcome":           { "type": "string", "minLength": 1 },
    "current_workaround":        { "type": ["string", "null"] },
    "success_criteria":          { "type": "string", "minLength": 1 },
    "frequency":                 { "type": ["string", "null"] },
    "who_is_affected":           { "type": "string", "enum": ["requestor", "team", "multiple_teams", "customers"] },
    "time_cost":                 { "type": ["string", "null"] },
    "deadline":                  { "type": ["string", "null"] },
    "systems_involved":          { "type": "array", "items": { "type": "string" } },
    "data_sensitivity":          { "type": "string", "enum": ["none", "internal", "customer", "financial", "regulated", "unspecified"] },
    "customer_facing":           { "type": ["boolean", "null"] },
    "solution_idea":             { "type": ["string", "null"] },
    "attachments":               { "type": "array", "items": { "type": "string" } },
    "context_constraints_nuance":{ "type": ["string", "null"] },
    "acceptance_criteria":       { "type": "array", "items": { "type": "string" } },
    "transcript_reference":      { "type": ["string", "null"] }
  }
}
```

### Beyond schema-validity: assertions per case

Schema-valid is necessary but not sufficient. Each extraction case also asserts:

1. **No invented values.** Every populated field traces to something the transcript
   states. Nullable-but-absent → `null`; routing enums → `unspecified` (sensitivity) or
   `null` (customer_facing), never a confident guess.
2. **Auto-fill verbatim.** `requestor` / `team` / `date` / `transcript_reference` match the
   supplied `[Auto-filled]` values exactly; never authored by the model.
3. **No prose.** Output is the JSON object only, with no preamble, summary, or fences.
4. **Sensitivity floor.** If sensitivity is absent from the transcript, output is
   `"unspecified"`; `"none"` on an unstated transcript is a fail.

## D. Extraction half: cases

| # | Input transcript | Key assertions |
|---|---|---|
| E1 | Rich transcript (deal→checklist; customer data in, internal out; ~20 min, few/week; Zapier idea) | All fields populated; `data_sensitivity="customer"`; `customer_facing=false`; `solution_idea` present but flagged non-binding; AC array of 3 |
| E2 | Sparse transcript (manual Monday reporting; sensitivity & customer-facing never discussed) | `data_sensitivity="unspecified"`; `customer_facing=null`; `time_cost=null`; `systems_involved=[]`; `acceptance_criteria=[]`; nothing invented |
| E3 | Transcript naming two systems + a deadline + an attachment link | `systems_involved` has both; `deadline` captured as stated; `attachments` non-empty |
| E4 *(adversarial)* | Transcript where the requestor speculates about cost ("probably cheap") and a vendor name | Speculation does NOT leak into any field; vendor only in `solution_idea` if the requestor proposed it as their idea |

> **CI rule (from best practices §9):** a prompt edit that regresses these scores blocks
> the merge; evals are treated like unit tests.
