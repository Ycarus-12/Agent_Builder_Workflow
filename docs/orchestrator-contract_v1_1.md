---
artifact: orchestrator-contract
version: 1.1.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Developer-facing specification of the deterministic application layer that sequences,
  routes, gates, logs, and runs every agent in the tool-request workflow. Defines the
  shared invocation contract every agent prompt plugs into, the intake-specific
  contract the two intake prompts already lean on, the validate-and-retry loop for
  structured outputs, the sensitivity overlay, and the eval harness shape.
type: specification (not a prompt)
covers:
  - intake-conversation v1.0.0
  - intake-extraction v1.0.0
  - intake-evals v1.0.0
  - stack-check v1.0.0
  - triage-recommender v1.1.0
  - cost-estimation-rom v1.1.0
  - cost-estimation-deepdive v1.0.0
  - build-agent v1.0.0
  - functional-qa v1.0.0
  - security-vulnerabilities v1.0.0
  - security-governance v1.0.0
  - portfolio-pattern v1.0.0
  - registry-maintenance v1.0.0
dependencies:
  - Architecture & Process Specification v0.3 §3 (Orchestrator role), §4 (workflow),
    §5 (intake), §8 (gates), §10 (agent specs), Appendix A (intake schema)
  - Prompt-Authoring Best Practices §4 (handoff contract), §6 (orchestrator contract),
    §7 (versioning), §9 (eval thresholds)
changelog: >
  v1.1.0 sequenced the analysis stage (stack_check -> triage -> cost_rom); updated
  gate_1a to accept N selections; generalized cost_deepdive to N options; clarified
  context attachment for ROM and deep-dive in §3.2. Consolidated from the v1.0 base +
  v1.1 amendment into a single document.
  v1.0.0 initial draft.
---

# Orchestrator Contract (v1.1.0)

## 1. Purpose & scope

The orchestrator is the application layer that moves work between agents. It is
**deterministic code**, never a model: it sequences stages, attaches the right context
to each agent call, enforces the human gates, detects handoff signals, validates
structured outputs, retries on failure, and logs everything. It holds no judgment of
its own. Judgment is delegated to agents; routing, sequencing, and gating are not.

This document is the **contract** every agent assumes. It is a specification for
developers building the application, not a prompt and not a model artifact.

In scope:

- The pipeline state machine and the stop list.
- The shared agent-invocation contract (input envelope, output handling, context
  attachment, logging) every agent prompt plugs into.
- The intake-specific contract that the two intake prompts already lean on.
- The validate-and-retry loop for any agent emitting structured output.
- The sensitivity-overlay enforcement rule.
- The eval-harness shape: fixture format, assertions, conversation hard-fail
  detection, and the CI rule.

Out of scope: model selection, prompt content, provider routing (the AI gateway
handles that), and the deferred items called out in §9.

## 2. The pipeline state machine

The orchestrator is a state machine with the stages below. Transitions are
deterministic except where a human gate is explicitly listed.

States, in order:

1. `intake_open`: conversation in flight with the requestor.
2. `intake_extract`: closed transcript being turned into a structured record.
3. `analysis`: sequential sub-pipeline. Runs `stack_check`, then `triage`, then
   `cost_rom`, in that order. Triage produces a costable short list of 1–4 named
   options (always — including for route-elsewhere and don't-build recommendations);
   ROM costs each option one-to-one. The costed list is the analysis package handed
   to `gate_1a`.
4. `gate_1a` *(human: Director)*: review the costed short list. Decision shape: pick
   1 or more options for deep-dive; OR accept the triage recommendation directly
   (terminates for route-elsewhere/don't-build, proceeds-as-configured otherwise); OR
   reject and send back for re-triage with notes. The orchestrator routes per the
   Director's selection.
5. `cost_deepdive`: detailed cost on each option the Director selected at `gate_1a`
   (1 to N). When N > 1, the agent additionally produces an across-options
   recommendation. Skipped entirely when the Director accepted a route-elsewhere or
   don't-build recommendation at `gate_1a` (the request terminates after `gate_1a` in
   those cases).
6. `gate_1b` *(human: Director)*: approve the spend.
7. `build`: self-serve lane builds; heavy apps route to R&D.
8. `qa_functional`: functional QA; failures loop back to `build`.
9. `security_review`: two security agents plus deterministic scanners; heavy or
   sensitive work also takes the R&D security sign-off.
10. `gate_2` *(human: Director)*: accept the finished tool.
11. `deploy_and_register`: terminal. Tool deployed, owner and review date assigned,
    registry updated.

**The stop list (the only states that can halt a request):**

- Requestor sign-off, at the close of `intake_open` (confirming their own request).
- `gate_1a`, `gate_1b`, `gate_2` (Director).
- The R&D security sign-off within `security_review`, on heavy or sensitive work.

Every other state advances when its work completes. Nothing else blocks.

**Triage recommendations the Director may approve at `gate_1a`** include the
six-outcome cascade: route elsewhere (out of scope) | don't build | configure existing
tool | process or training fix | buy | build. The orchestrator does not select the
outcome; triage recommends and the Director decides.

Regardless of the recommendation, triage produces a 1–4 option short list and ROM costs
it before `gate_1a` fires. This keeps the analysis package shape consistent at the gate.
For a `route_elsewhere` or `don't_build` recommendation accepted at `gate_1a`, the
orchestrator records the decision (and the destination, for route-elsewhere), fires the
notify/hand-off where applicable, and terminates the request without entering
`cost_deepdive`.

If the Director rejects the triage recommendation at `gate_1a` and sends the request
back for re-triage, the orchestrator re-enters the `analysis` sub-pipeline at `triage`
(not at `stack_check`; the stack-check finding is still valid). Re-triage receives the
Director's notes as an additional input block. ROM runs again on the new option list.

## 3. The agent invocation contract

Every agent call obeys the same shape. This is what each agent prompt assumes about
its caller.

### 3.1 Input envelope

The orchestrator passes the agent a single context payload composed of named,
delimited blocks. Conventions:

- **XML-style delimiters** for mid/high-tier (Claude) agents: `<block_name> … </block_name>`.
- **Labeled bracket blocks** for SLM agents: `[Block Name]` followed by content.
- **Block names are stable and per-agent.** The intake-conversation agent receives
  `<requestor_identity>` and `<conversation>`; the intake-extraction agent receives
  `[Auto-filled]` and `[TRANSCRIPT]`. Each future agent declares its own block names
  in its prompt; the orchestrator supplies exactly those blocks, nothing else.
- **No silent injections.** The orchestrator never appends instructions to an agent
  beyond the named blocks. Anything that needs to reach the agent is a named block.

### 3.2 Context attachment policy

The orchestrator attaches context **per stage by deterministic rule**, scaled to what
the stage needs. Per the architecture's spend-tokens-where-judgment-justifies-it
principle:

- **Stages requiring nuance** (triage; downstream judgment agents) receive the **raw
  transcript** plus the structured extract.
- **Mechanical stages** (extraction; ROM cost; stack-check matching) receive only the
  **structured extract** plus stage-specific inputs.
- **The ROM stage receives the structured extract plus triage's costable option short
  list.** It does not receive the raw transcript (mechanical classification per
  option); it does not receive the stack-check finding directly (triage already
  factored that into the option list).
- **The deep-dive stage receives the structured extract, the raw transcript, the
  stack-check finding, the ROM output, and the Director's selected subset of options
  from `gate_1a`.** Deep-dive is a judgment stage and gets the full context.

Attachment is rule-based, not model-judged.

### 3.3 Output handling

Two output modes, decided per agent:

- **Prose (human-facing).** The agent's text is forwarded to the requestor or
  surfaced to the Director. The orchestrator scans the text only for declared
  handoff signals (e.g., the intake sign-off marker, §4.3). It does not parse, edit,
  or summarize prose.
- **Structured (machine-facing).** The agent emits JSON via constrained decoding
  (structured outputs / strict tool use, forced exactly once). The orchestrator
  validates against the declared schema and runs the retry loop (§5).

A single agent is one mode or the other, never both. The intake-conversation agent
is prose; the intake-extraction agent is structured.

### 3.4 Versioning & logging at the call site

Every agent call logs:

- The agent name and **prompt version + commit hash** (so a trace links back to the
  exact prompt that produced the output).
- The input envelope, redacted per data-sensitivity rules.
- The output (prose or structured), redacted per data-sensitivity rules.
- Validation result, retry count, and timing.
- The conversation/request ID and stage.

This is the audit-trail the architecture requires; it lives in the application, not
the gateway.

## 4. The intake-specific contract

The two intake prompts (`intake-conversation` v1.0.0 and `intake-extraction` v1.0.0)
already lean on the behaviors below. This section makes them concrete.

### 4.1 Identity resolution & auto-fill

`requestor`, `team`, `date`, and `transcript_reference` are **never authored by the
model**. The orchestrator supplies them:

| Field | Source |
|---|---|
| `requestor` | Authenticated session identity from the SSO / identity provider. |
| `team` | Team/department attribute on the SSO directory record. |
| `date` | System clock at the moment intake opened (ISO-8601, system timezone). |
| `transcript_reference` | Stable identifier minted by the orchestrator when it persists the closed transcript. |

The intake-conversation agent receives `requestor` and `team` inside
`<requestor_identity>` so it can address the person by name without asking. The
intake-extraction agent receives all four inside `[Auto-filled]` and is instructed to
copy them verbatim into the JSON record.

### 4.2 The conversation loop

The intake-conversation agent is stateless. The orchestrator manages the running
conversation:

1. On a new request, the orchestrator opens a session, mints a session ID, and
   captures the requestor's identity.
2. On each requestor turn, the orchestrator constructs the input envelope:
   `<requestor_identity>` (constant for the session) and `<conversation>` (the full
   running turn history).
3. The orchestrator sends the envelope to the agent and forwards the agent's prose
   response back to the requestor.
4. The orchestrator appends the new turn pair to the conversation buffer and returns
   to step 2 on the next requestor message.
5. The session continues until the marker fires (§4.3) or the orchestrator times out
   the session (§4.5).

The conversation buffer is the **draft transcript**; on marker detection it becomes
the **persisted transcript** of record.

### 4.3 Marker detection

The intake sign-off marker is the literal string `[[INTAKE_SIGNOFF_CONFIRMED]]`. The
orchestrator detects it deterministically with the following rule:

- The marker must appear as the **final non-empty line** of an agent response, with
  no other content on that line.
- A response containing the marker anywhere other than the final line is logged as
  a marker-misuse event and treated as a normal conversational turn (the orchestrator
  does **not** advance to extraction).
- Multiple marker occurrences in a single response are likewise treated as misuse.
- The marker is detected by exact string match. The orchestrator does not parse the
  prose for semantic confirmation. If the marker appears without the prior requestor
  turn containing an explicit confirmation, that is a **conversation hard fail**
  caught by the eval harness (§7.3), not something the orchestrator second-guesses
  at runtime.

On a valid marker:

1. Persist the transcript at the orchestrator-minted `transcript_reference`.
2. Strip the marker line from the requestor-visible final turn.
3. Transition to `intake_extract` and invoke the extraction handoff (§4.4).

### 4.4 The extraction handoff

The orchestrator invokes the intake-extraction agent **once** per intake session,
with:

- `[Auto-filled]` block: the four orchestrator-supplied fields.
- `[TRANSCRIPT]` block: the full persisted transcript.

The agent emits JSON via the structured-output tool, forced exactly once. The
orchestrator runs the validate-and-retry loop (§5). On success, the structured record
is stored alongside the transcript, both fields now in scope for downstream stages.

### 4.5 Session timeout & abandonment

If the requestor stops responding before the marker fires, the orchestrator times
the session out per a configurable policy (recommend: 7 days inactivity). A timed-out
session does **not** advance to extraction; it is logged as `intake_abandoned` and
surfaced on the Director's daily digest. The intake-conversation agent is **not**
asked to self-close; abandonment is an orchestrator concern, not an agent concern.

## 5. The validate-and-retry loop

Every structured-output agent uses the same loop. The intake-extraction agent is the
first instance; future structured agents inherit it.

```
INVOKE agent with input envelope
ATTEMPT = 1
LOOP:
  RECEIVE output
  VALIDATE output against declared JSON Schema
  IF valid: return output
  ELSE:
    LOG validation failure (schema errors, attempt number)
    IF ATTEMPT >= MAX_ATTEMPTS:
      EMIT escalation event (see below)
      RETURN failure (do not silently proceed)
    ATTEMPT += 1
    RE-INVOKE agent with the original envelope plus a [Validation feedback] block
      naming the specific schema violations
    LOOP
```

Recommended initial settings:

- `MAX_ATTEMPTS = 3` (initial + 2 retries). Tunable per agent.
- **Validation feedback block** on retry: a labeled block listing the schema errors
  (path, message), prepended to the retry envelope so the agent can correct rather
  than guess.
- **No silent fallback to a larger model.** Escalation is explicit (see below).

**Escalation on exhausted retries:**

1. Log the failure with full input envelope, all attempt outputs, and schema errors.
2. Surface to the Director as a `structured_output_failed` event.
3. Pause the request at its current stage; do not advance, do not silently drop.
4. The Director's options: re-run, escalate the subtask to a larger model per the
   "escalate, don't force" principle in best practices §3b, or fix the prompt and
   re-test against evals.

## 6. The sensitivity overlay

The intake-extraction prompt is instructed to emit `data_sensitivity = "unspecified"`
when the transcript does not establish sensitivity. The orchestrator enforces the
downstream meaning of that value:

- **`"unspecified"` is treated as sensitive-until-confirmed.** Functionally
  equivalent to `"customer"` for routing decisions in the current pipeline.
- It **does** force the security review (both agents) on any build.
- It **does** force the R&D security sign-off on heavy builds (heavy + unspecified
  is treated as heavy + sensitive).
- It **does not** silently downgrade to `"none"` anywhere in the pipeline.

If a downstream stage needs the actual sensitivity (e.g., to scope a security
review more narrowly), the orchestrator routes the request back to the Director for
classification rather than to the requestor or an agent. Classification is a
judgment call the Director owns.

The data-sensitivity field, once resolved, never changes the **route** (the
architecture's overlay principle); it only raises the guardrails on whatever is
built.

## 7. The eval harness

The orchestrator owns the test harness that runs the eval scaffolds (`intake-evals`
v1.0.0 is the first; every agent will have one).

### 7.1 Fixture format

One fixture per case, stored alongside the eval artifact in the registry repository.

**Conversation fixtures** (one file per scenario C1–C6):

```yaml
case_id: C1
agent: intake-conversation
version: 1.0.0
description: Requestor opens with a named tool ("build me a Zapier zap")
auto_filled:
  requestor: "Test User"
  team: "Test Team"
  date: "2026-06-26"
turns:
  - role: requestor
    content: "I need you to build me a Zapier zap."
  - role: requestor   # follow-up after the agent's response
    content: "Every time a deal closes in the CRM I have to manually make a kickoff checklist."
  # ... continue until the scenario reaches its terminal state
expected_terminal_state: marker_fired | conversation_in_progress | hard_fail_<kind>
```

**Extraction fixtures** (one file per case E1–E4):

```yaml
case_id: E1
agent: intake-extraction
version: 1.0.0
description: Rich transcript, deal->checklist
auto_filled:
  requestor: "J. Rivera"
  team: "Professional Services"
  date: "2026-06-25"
  transcript_reference: "txn/2026-06-25/rivera-01"
transcript: |
  Requestor: Every time a deal closes in the CRM I make a kickoff checklist by hand...
  [full transcript inline]
assertions:
  schema_valid: true
  field_assertions:
    data_sensitivity: "customer"
    customer_facing: false
    solution_idea_present: true
    acceptance_criteria_length: 3
    systems_involved_contains: ["CRM", "work-management tool"]
  auto_fill_verbatim: true
  no_prose_outside_json: true
```

### 7.2 Assertion runners

**Extraction (fully automated, every commit):**

1. Run the extraction agent against each fixture's transcript and auto-fill block.
2. Validate the output against the JSON Schema from `intake-evals` §C.
3. Evaluate each field assertion declared in the fixture.
4. Check `auto_fill_verbatim` (orchestrator-supplied fields appear unchanged in
   output).
5. Check `no_prose_outside_json` (response is the JSON object only, no fences,
   preamble, or trailing text).
6. Aggregate to a per-case pass/fail; fail the build on any case failing.

**Conversation hard-fails (automated, every commit):**

For each conversation fixture, run the agent against the scripted turns and check:

- **Marker without confirmation:** marker appeared, but the immediately prior
  requestor turn did not contain an explicit confirmation token (`yes`, `correct`,
  `that's right`, `confirmed`, or equivalent per a configurable list).
- **Marker placement:** marker not on the final non-empty line, or appears more
  than once.
- **Scope-or-route violation:** agent's prose contains patterns indicating it
  judged scope or routed the request (e.g., "that's a job for IT", "this isn't a
  tool request", "I'll route this to"). Pattern list lives in the eval harness
  config.
- **Feasibility/cost/timeline promises:** patterns like "this will cost", "we can
  build that in", "by next week". Pattern list lives in the eval harness config.
- **Multiple-questions-per-turn:** detected by question-mark count above a
  threshold per turn (soft signal, not a hard fail; surfaced on a daily report).

Hard-fail patterns are **deterministic checks**, not judge-model calls. False
positives are tuned by editing the pattern list, which is itself an audited artifact.

**Conversation rubric scoring (semi-automated, pre-merge on prompt changes):**

- Out of scope for every-commit CI.
- Runs on a schedule (weekly) and on every PR that touches the prompt.
- Implemented as a **judge model** call: a grader prompt receives the conversation
  transcript and the rubric definition, returns a per-dimension score (1-5) and
  rationale. Recommend running it three times per case and reporting median to
  reduce judge variance.
- Human spot-check on a sample each release.

### 7.3 The CI rule

Per best-practices §9, a prompt edit that regresses eval scores blocks the merge.
Concretely:

- **Extraction case fails** → merge blocked.
- **Conversation hard fail** → merge blocked.
- **Conversation rubric median drops below 3 on any dimension, or below the previous
  baseline by more than 1 point on any dimension** → merge blocked.
- **Rubric improves** → new baseline recorded.

The harness records the prompt version + commit hash on every run so regressions are
traceable to the change that introduced them.

## 8. Logging & audit

The orchestrator logs the following events with timestamps and request/session IDs:

| Event | Captured fields |
|---|---|
| Agent call (any) | Agent name, prompt version + commit hash, stage, redacted input envelope, redacted output, validation result, retry count, latency. |
| Marker fired | Session ID, transcript reference, agent version. |
| Marker misuse | Session ID, agent output, classification (non-final-line, multiple, no-prior-confirmation if detected). |
| Validation failure | Stage, agent, attempt number, schema errors, redacted output. |
| Retry exhausted (escalation) | All attempt outputs, schema errors, surface-to-Director acknowledgment. |
| Gate decision | Stage (1a/1b/2/R&D), decision, decided-by, rationale text, timestamp. |
| Sensitivity overlay applied | Original value, effective value, triggering stage. |
| Session abandoned | Session ID, last-active timestamp, configured timeout. |
| Registry update | PR number, change type (auto-merge vs. judgment), reviewer. |

Redaction follows the data-sensitivity rules: anything tagged `customer`, `financial`,
`regulated`, or `unspecified` is redacted by default in log payloads; only the
metadata is retained at-rest. Full payloads are available only behind an access
control distinct from the application's runtime credentials.

The audit trail lives in the application database. **The AI gateway is not the
system of record for audit;** it is a router only.

## 9. Out of scope for v1

The following are deliberately deferred and not specified here. Each is a known gap;
none blocks v1.

- **Queueing & parallelism.** v1 assumes sequential processing of a request through
  its pipeline; multiple requests in flight are independent. No agent fan-out, no
  parallel triage and cost.
- **Distributed tracing & observability tooling.** Logs as specified are sufficient
  for audit and debugging; OpenTelemetry, dashboards, and alerting are deferred.
- **Error recovery beyond bounded retry.** Network errors, gateway failures, and
  agent timeouts are caught and surfaced; recovery policy (auto-retry the call,
  fail the stage, requeue) is per-failure-class and lives in the implementation.
- **Multi-tenant isolation.** v1 scope is the Director's team only (per the
  architecture's registry scope). Cross-team or org-wide deployment is a v2 concern.
- **Gateway selection.** The production-grade compliant gateway is an open decision
  (Architecture §15). v1 dev/test runs against OpenRouter with BYOK; production
  swaps the gateway without contract changes.
- **Live runtime adaptive thinking & effort tuning per agent.** The recommended
  thinking and effort settings live in each agent's prompt artifact metadata; the
  orchestrator passes them through. Adaptive tuning based on observed performance
  is deferred.
- **A pre-intake out-of-scope classifier.** Currently a data-driven open decision:
  the portfolio agent will cluster `route_elsewhere` outcomes from triage, and if
  the cluster grows large enough, a cheap pre-intake classifier becomes
  data-justified. v1 routes everything through intake.

## 10. Metadata footer

- **Artifact:** `orchestrator-contract`
- **Version:** `1.1.0` · **Owner:** Director · **Status:** Draft
- **Type:** Specification (not a prompt; not a model artifact)
- **Covers:** all ten agents (intake-conversation/extraction, stack-check, triage-recommender, cost-estimation-rom/deepdive, build-agent, functional-qa, security-vulnerabilities/governance, portfolio-pattern, registry-maintenance) plus their eval suites.
- **Changelog:** `v1.1.0` sequenced the analysis stage (`stack_check` → `triage` → `cost_rom`); updated `gate_1a` to accept N selections; generalized `cost_deepdive` to N options; clarified context attachment for ROM and deep-dive in §3.2; consolidated the v1.0 base + v1.1 amendment into one document. `v1.0.0` initial draft.
