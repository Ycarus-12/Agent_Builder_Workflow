# PART 2 — PROJECT CONTEXT

> **Snapshot date:** 06/29/2026 · **Owner:** Director · **Supersedes:** context_06_25.md
> **State:** Architecture, contracts, and all agent prompts + eval suites are authored,
> integration-verified, and internally consistent. The project is at the **build gate** —
> the next phase is coding the application, not authoring more specs.

## 1. Summary

An internal, agent-led system for intaking tool/AI build requests and carrying each from
request to deployed tool. It is a standalone, org-shareable application built on a
provider-neutral model layer (an adopted AI gateway) and a GitHub-backed capability
registry. Ten LLM agents do the work; a deterministic orchestrator moves work between
them; the Director is the only human who decides what gets built, bought, or declined.

## 2. Current state

- **Architecture: consolidated at v0.3** (`Agentic_Tool-Request_Workflow_Architecture_v0_3.docx`).
  v0.3 sequenced the analysis stage and redefined triage's output as a costable option
  short list (see §3).
- **Orchestrator contract: consolidated at v1.1.0** (`orchestrator-contract_v1_1.md`).
  The v1.0 base and the v1.1 amendment are merged into one document; both predecessors
  are retired.
- **All ten agents authored, prompt + eval suite each, all on the v0.3 / v1.1 baseline.**
  The full corpus has passed an end-to-end integration pass: every handoff seam matches
  producer-to-consumer, the build-avenue/engine/weight/route vocabulary is uniform, and
  each eval suite covers the current version of the agent it tests.
- **Security duplication resolved.** The keeper set is `security-vulnerabilities` +
  `security-governance` (two lenses) with one combined `security-evals` suite. The
  earlier parallel `security-data-governance` set was retired.
- **Parking lot: clear.** No open item blocks coding; the remaining open decisions
  (§6) are deferred on purpose.

## 3. The pipeline (advisory analysis; the Director decides)

The analysis stage is **sequential**, not parallel:

Intake → **stack-check → triage → ROM** → **Director Gate 1a** → deep-dive cost →
**Director Gate 1b** → Build → Functional QA → Security review (+ R&D sign-off if
heavy/sensitive) → **Director Gate 2** → Deploy & register.

**The costable option short list (the v0.3 contract).** Triage produces two things on
every request: a short list of **1–4 route-typed options** (`configure` / `build` /
`buy`), each named precisely enough to cost, and a single **recommendation** (one of the
six cascade outcomes) that points into the list via `recommended_option_id`. ROM costs
each option one-to-one. The list is always produced — for route-elsewhere, don't-build,
or process-training-fix recommendations it holds the notional option(s) and
`recommended_option_id` is null. At Gate 1a the Director picks one or more options for
deep-dive, accepts the recommendation directly, or sends it back for re-triage.

**The stop list** (the only places a request can halt): requestor sign-off; Director
Gate 1a / 1b / 2; R&D security sign-off on heavy/sensitive. Everything else is advisory.

## 4. The agents (10 + deterministic orchestrator)

| Agent | Role (one line) | Model tier | Artifacts |
|---|---|---|---|
| Intake | Live conversational capture + separate extraction pass; never blocks/decides | Mid (conversation) + SLM (extraction) | `intake-conversation`, `intake-extraction`, `intake-evals` |
| Stack-check | "Do we already own this?" matched to the registry | Mid + retrieval | `stack-check`, `stack-check-evals` |
| Triage / recommender | Six-outcome cascade → 1–4 costable options + a recommendation | Large / frontier | `triage-recommender` v1.1.0, `triage-evals` v1.1.0 |
| Cost — ROM | Costs each triage option one-to-one (bands only) | SLM | `cost-estimation-rom` v1.1.0 |
| Cost — deep-dive | Detailed cost on each Director-selected option (1..N) | Mid-large + web | `cost-estimation-deepdive`, `cost-estimation-evals` |
| Build | Builds to the approved option along the assigned avenue | Large / frontier (coding) | `build-agent`, `build-evals` |
| Functional QA | Runs build to spec; functional only; separate from build | Mid-large + execution | `functional-qa`, `functional-qa-evals` |
| Security — vulnerabilities | Secure-coding review | Large / frontier | `security-vulnerabilities` (+ `security-evals`) |
| Security — data governance | Data handling, access, isolation, regulated-data | Large / frontier | `security-governance` (+ `security-evals`) |
| Portfolio / pattern | Daily theme clustering; build vs. enablement signal | Embeddings + mid LLM (batch) | `portfolio-pattern`, `portfolio-pattern-evals` |
| Registry maintenance | Keeps the registry current; PR-based updates | SLM + mid (batch) | `registry-maintenance`, `registry-maintenance-evals` |
| Orchestrator (not an agent) | Sequencing, routing, gating, logging | Deterministic, no model | `orchestrator-contract` v1.1.0 |

**Sizing principle:** spend frontier-model tokens only where judgment, code, or security
justify it; small models for capture, extraction, matching, and the ROM; deterministic
for control flow.

## 5. Canonical vocabulary (locked — coders implement these enums verbatim)

These token sets are uniform across every agent, eval, and contract. They are the
machine-facing enums; English prose may capitalize naturally (e.g., "AI engine").

- **route** (option route-type): `configure` | `build` | `buy`
- **outcome** (triage recommendation): `route_elsewhere` | `dont_build` | `configure` | `process_training_fix` | `buy` | `build`
- **build_type / avenue**: `code` | `agent_creation` | `config_applied` | `config_instructions` (underscored; no `instructions-only`)
- **engine**: `ai` | `deterministic` (lowercase)
- **weight**: `light` | `heavy` (carried on each build option; replaces the older `lane` field)
- **data_sensitivity**: `none` | `internal` | `customer` | `financial` | `regulated` | `unspecified`
- **support** (registry capability): `native` | `configurable` | `not_supported`
- **status** (registry record): `Planned` | `In build` | `In pilot` | `In use` | `Deprecated`
- **sign-off marker**: the literal string `[[INTAKE_SIGNOFF_CONFIRMED]]`, emitted by intake-conversation only on explicit requestor confirmation, on the final line.

## 6. Locked decisions (do not re-litigate)

**Workflow & control**
- Standalone app, org-shareable, provider-neutral, tool-agnostic, unbranded.
- Intake is capture-only and never blocks or decides. Analysis is advisory. The Director
  is the sole decision-maker. No override mechanism — nothing auto-blocks.
- Acceptance criteria are drafted during intake and approved by the requestor before the
  request reaches the Director.

**Intake**
- Agent-led live conversation, not a form; captures the problem, not a prescribed
  solution. Extraction is a separate, cheaper SLM pass; the raw transcript persists as
  the durable record and the structured extract is an index over it.
- `build_type` is NOT an intake field — it is a downstream classification supplied by the
  orchestrator. (Two security prompts originally read it off the intake extract; fixed.)

**Triage & analysis**
- Six-outcome cascade, cheapest filters first: route-elsewhere → don't-build → configure
  → process/training-fix → buy → build.
- Triage emits a 1–4 costable option short list PLUS one recommendation across it (v0.3).
  ROM costs the list one-to-one. Gate 1a takes N selections into deep-dive.
- The registry `support` tag is the hinge: native/configurable → configure;
  not_supported → build/buy.
- Data-sensitivity overlay raises guardrails; it never changes the route. `unspecified`
  is treated as sensitive-until-confirmed (equivalent to `customer` for routing).

**Cost**
- ROM (bands only, no dollars) costs each triage option; deep-dive (web pricing, 1..N
  options) runs after Gate 1a with an across-options recommendation when N > 1. Labor in
  hours + token bands; the Director converts at the gate.

**Build, QA & security**
- Build avenues: `code`, `agent_creation`, `config_applied`, `config_instructions`.
  Config-instructions ships a guide flagged "unverified — validate on apply."
- Functional QA is a separate agent from build; functional scope only.
- Two security agents (vulnerabilities + data governance), distinct lenses, run blind to
  each other and reconciled by the orchestrator; backed by deterministic CI scanners.
  Critical findings block and escalate; a disagreement routes to the Director. Security
  is non-bypassable, including by the Director.

**Provider strategy**
- Provider-neutral seam realized by adopting an AI gateway (buy, not build). Multi-provider
  built in from day one; operate single-provider (Anthropic) to start. Dev/test:
  OpenRouter + BYOK, fallback disabled, $50/mo cap, synthetic/sanitized data only.
  Production swaps to a self-hostable/compliant gateway before any real data.

**Registry, portfolio, audit**
- GitHub-backed private registry: one YAML record per file, PR-based change/audit trail;
  hybrid granularity (record + nested capability statements); demand-driven growth.
- Portfolio agent runs daily, clusters themes against the registry (build vs. enablement),
  applies tiered thresholds, and flags pseudo-agent graduation.
- Audit lives in the application, never the gateway. Every agent call logs prompt version
  + commit hash. Validate-and-retry (bounded, default 3) on structured outputs; on
  exhaustion, escalate to the Director — never silently fall back to a larger model.

## 7. Open decisions (deferred on purpose; none blocks coding)

1. Which production-grade compliant gateway to adopt, and on what data-governance terms.
2. Which additional model providers to add per agent, and when (data-driven).
3. The specific build-environment infrastructure (with R&D); ephemeral-container lean not finally locked.
4. The specific scanner tool selection and CI plumbing (with R&D).
5. The registry inventory-source integration specifics (which SSO/app-catalogue, and its API).
6. Whether/when to add a cheap pre-intake out-of-scope classifier (data-driven via portfolio clustering).
7. Whether/when to introduce a blended labor rate for dollar-denominated cost output.
8. Tuning of the recurring-theme thresholds (set initially, refined with data).

## 8. Glossary (delta from prior snapshots)

- **Costable option short list** — triage's primary output: 1–4 route-typed options
  (`configure`/`build`/`buy`) each named precisely enough for ROM to cost.
- **Recommendation** — the single cascade outcome triage recommends across the option
  list; points into the list via `recommended_option_id` (null for non-build outcomes).
- **Notional option** — for a route-elsewhere/don't-build/process-fix recommendation, the
  option(s) that would have been pursued, still costed so Gate 1a sees a consistent package.
- **Sequential analysis** — stack-check → triage → ROM run in order; ROM costs triage's
  list; the costed list is the Gate 1a package. (Replaces the older "parallel package.")
- **Re-triage** — if the Director rejects at Gate 1a, the orchestrator re-enters analysis
  at `triage` (not stack-check; the finding still holds), with the Director's notes attached.

## 9. Next steps — the build phase

Authoring is done. The remaining work is building the application:

1. **Stand up the registry repository** (GitHub, YAML schema per Architecture Appendix C,
   foldered by record type). It is the largest dependency — stack-check, triage,
   portfolio, and registry-maintenance all read it.
2. **Build the deterministic orchestrator** to `orchestrator-contract_v1_1.md`: the state
   machine, input-envelope assembly, context-attachment rules (§3.2), validate-and-retry
   (§5), sensitivity overlay (§6), marker detection, and logging (§8).
3. **Adopt the dev/test gateway** (OpenRouter + BYOK per the locked posture).
4. **Wire the eval harness** (§7) so every agent's eval suite runs in CI as the merge gate.
5. **CI scanners and execution environments** for the build/QA/security stages — both
   flagged R&D-dependent (open decisions 3–4), so they can follow the core spine.

Suggested order: registry repo → orchestrator spine → one agent wired end-to-end against
the gateway (intake is the natural first) → eval harness in CI → remaining agents.
