**Agentic Tool-Request Workflow**

Architecture & Process Specification

*Provider-neutral · tool-agnostic · agent-led, human-gated*

| Field | Value |
| --- | --- |
| **Version** | 0.3 |
| **Date** | 06/29/2026 |
| **Owner** | Director (Workflow Owner) |
| **Status** | Draft |
| **Author** | Director (Workflow Owner) |
| **Confidentiality** | INTERNAL |

# 1. Purpose & Scope

This document defines the architecture and process for an agentic workflow that lets team members request tools — including AI tools — and moves each request from intake through analysis, a human decision, build, quality assurance, security review, and deployment. The workflow is agent-led wherever judgment can be delegated, with a single human decision authority over what is built, bought, or declined.

The design is deliberately **provider-neutral** and **tool-agnostic**: no model vendor or named product is hard-wired into the architecture, so the system starts from a blank slate and any specific choice is recorded as a decision rather than an assumption.

### In scope

- The end-to-end request lifecycle and the human decision points within it.
- The agents, their responsibilities, and prompt-ready specifications.
- The supporting capability registry, the provider and model strategy, and the system's dependencies.

### Out of scope

- Agent prompt text, which is a downstream build artifact authored from these specifications.
- Vendor-specific implementation detail, except where a starting choice is explicitly recorded.

# 2. Design Principles

Every decision in this document follows from a small set of principles. Where a later choice seems arbitrary, it traces back to one of these.

- **Agent-led, human-gated.** Agents do the work wherever judgment can be delegated; humans decide where it matters.
- **Problem before solution.** Intake captures the underlying problem, not the solution the requestor has in mind, so analysis can reframe.
- **Cheapest filters first.** Triage eliminates the no-build and reuse outcomes before spending effort on the expensive build-versus-buy question.
- **One decision authority.** The Director decides on every request. Intake never blocks a request, so no override mechanism is needed.
- **Security is never bypassed.** Security review and the heavy-app sign-off cannot be waived by anyone, including the Director.
- **Deterministic plumbing, model-based judgment.** Control flow, routing, and logging are deterministic code; models are used only where reasoning, language, or judgment is required.
- **Defer complexity until data earns it.** Build the seams now (provider neutrality, reuse loop) but adopt the simpler operating posture first and expand only when usage justifies it.
- **Reuse before rebuild.** The registry lets analysis match a request to something that already exists before anything new is built.
- **Everything auditable.** Every gate decision, security finding, and registry change is logged and reviewable.

# 3. Roles & Responsibilities

Four roles operate the workflow. Three are human or functional; the fourth is the deterministic application layer that moves work between them.

### Requestor

Submits a request through the intake conversation and confirms the captured scope and acceptance criteria. A requestor's submission can never be stopped at intake — capture always completes and always moves forward.

### Director (Workflow Owner)

The sole decision authority. The Director picks a direction (Gate 1a), approves spend (Gate 1b), accepts the finished tool (Gate 2), reviews any disagreement between the two security agents, and owns the capability registry. Because every request already routes through the Director, there is no override mechanism — there is nothing to override.

### Engineering / R&D function

Builds heavy applications, owns the security sign-off on heavy or sensitive work, and owns the underlying infrastructure choices — build environments, scanner tooling, and CI plumbing. For a heavy app, the Director's only action is approving the handoff; R&D owns the security approval.

### Orchestrator (deterministic, non-agent)

The application's state machine. It sequences stages, routes work to the Director's decision points, enforces the gates, and logs every action. It uses no model — it is fixed, auditable code, not an agent.

# 4. End-to-End Workflow

A request flows through the stages below. Analysis is advisory throughout; the Director is the only party who decides what proceeds.

| Stage | What happens |
| --- | --- |
| Intake | Conversational capture; never blocks or decides. Produces the structured request, draft acceptance criteria, and a persisted transcript; ends with requestor sign-off. |
| Analysis (advisory) | Sequential: stack-check runs first; triage runs second and produces a short list of 1–4 costable options plus a recommendation; ROM runs third and costs each option. The costed list is the analysis package. |
| Director — Gate 1a | The Director picks one or more options from the costed short list to deep-dive, OR accepts the triage recommendation directly (terminating route-elsewhere/don't-build outcomes, or proceeding-as-configured when no deep-dive is needed), OR rejects and sends back for re-triage. |
| Deep-dive cost | A detailed cost breakdown runs on each direction the Director selected at Gate 1a (1 to N). When more than one direction is selected, the agent produces an across-options recommendation alongside the per-direction breakdowns. |
| Director — Gate 1b | The Director approves the spend, deciding on the deep-dive. |
| Build | The self-serve lane builds the tool to spec; heavy apps route to R&D. |
| Functional QA | Verifies the build runs and meets the spec; loops back to build on failure. |
| Security review | Two security agents review the build; heavy or sensitive work also takes an R&D security sign-off. |
| Director — Gate 2 | The Director accepts the finished tool against the acceptance criteria. |
| Deploy & register | The tool is deployed, assigned an owner and review date, logged, and registered so it can be reused. |

### The stop list

A request can only halt at these points. Everything else is advisory and cannot stop a request:

- Requestor sign-off, at the end of intake (confirming their own request).
- The Director's Gate 1a, Gate 1b, and Gate 2.
- The R&D security sign-off, on heavy or sensitive work only.

### Data-sensitivity overlay

The sensitivity of the data a request touches does not change its route. It raises the guardrails on whatever is built: it forces the security review, and heavy-plus-sensitive work additionally requires the R&D security sign-off.

# 5. Intake & Scoping

Intake is an agent-led, live conversation, not a form. It captures only — it never decides and never blocks. The agent interviews the requestor adaptively, steers solution-talk back toward the underlying problem, fills the intake output schema (Appendix A), drafts the acceptance criteria, and obtains the requestor's sign-off at the end of the conversation.

### Extraction as a separate, cheaper pass

Two jobs happen in intake. The conversation is interactive and needs a capable model running live. Extraction — turning the finished transcript into the structured record — is mechanical, so a small, cheap model makes a single pass to populate the schema once the conversation closes. Frontier-rate tokens are spent only on the conversation, not the form-filling.

### The transcript is the durable record

The raw conversation transcript persists as the source of truth, and the structured extract is an index over it rather than a replacement. Context loss is therefore structurally impossible: any downstream agent that needs nuance can read the conversation itself. To keep token spend down, the orchestrator attaches the full transcript only to stages that need judgment (such as triage) and gives mechanical stages (such as the ROM) only the structured extract.

# 6. Triage & Decision Logic

Triage is advisory. It analyzes the request and produces a recommendation; the Director decides. The analysis runs as a cascade of cheap filters that resolve the easy outcomes first — beginning with whether the request belongs to this workflow at all, before any effort is spent on the expensive build-versus-buy question. The full per-node heuristics are in Appendix B.

### The six-outcome cascade

| Question | Outcome if it resolves here |
| --- | --- |
| **Is this a tooling/software/AI matter, or does another function own it?** | **If another function — Route elsewhere (suggest owning team).** |
| Worth solving? | If not — Don't build (manual or dropped). |
| Does a tool we own fit? | If yes — Configure an existing tool. |
| Is it a process or training gap? | If yes — Process/training fix (no software). |
| Does buying beat building? | If yes — Buy new technology. |
| Otherwise | Build it (light self-serve lane, or heavy R&D lane). |

**Route elsewhere as an advisory outcome.** When the request is genuinely outside this workflow's scope (an IT, HR, facilities, or other-function matter), triage recommends routing the requestor to the owning team rather than running a build cascade. Like every triage outcome, this is **advisory**: the Director approves it at Gate 1a, and the requestor is never blocked at intake. Intake captures the request neutrally regardless of how it looks; only triage suggests the route, and only the Director seals it.

### Triage's output: a costable short list

Triage produces two things on every request: a **short list of 1–4 concrete options** the workflow could pursue, and a **recommendation** about which option (or non-build outcome) to prefer. The short list is *always* produced — even when the recommendation is route-elsewhere or don't-build, triage still names the notional option(s) that would have been considered, so ROM can cost them and the Director sees a consistent analysis package at Gate 1a.

Each option in the short list is named concretely enough to be costed:

- **Configure options** name the existing tool and the capability statement being leveraged (e.g., "Configure Work-Management Tool's CRM deal-close trigger").
- **Build options** name the avenue (code / agent_creation / config_applied / config_instructions), the engine (ai / deterministic), and the weight (light / heavy).
- **Buy options** name the vendor or vendor category and the capability being acquired.

The short list is capped at 4 options to keep Gate 1a tractable. Where genuine alternatives exceed four, triage selects the four it judges most worth costing.

### Build sub-decisions

- **Light vs. heavy.** Light builds (a prompt-defined agent, an automation, a small script) take the self-serve lane; heavy builds (full apps, complex integrations, or anything customer-facing or touching sensitive data at scale) route to R&D.
- **AI vs. deterministic.** Reasoning, language, and judgment call for a model; rules and structured, repeatable steps call for deterministic automation. This choice is the largest input to the run-cost estimate.

These sub-decisions are recorded *on each build option* in the short list, so ROM can cost the option as the specific build it is.

### The registry hinge

The support level recorded against each registry capability routes this tree directly: **native or configurable** points to Configure; **not supported** points to Build or Buy.

# 7. Cost Estimation

Cost is estimated in two stages so that expensive research is never spent on a direction that will not proceed.

- **Stage 1 — ROM.** Runs after triage produces its costable short list. Costs each option in the list with effort, run-cost, license, and maintenance bands plus per-option confidence and key drivers. Deliberately low token burn — enough to pick which option(s) deserve a deep-dive, no more.
- **Stage 2 — deep-dive.** Runs after Gate 1a on each option the Director selected for deep-dive (1 to N). Produces a detailed breakdown per option — phased effort, concrete run-cost, maintenance, assumptions, and risks — with web access for current pricing. When more than one option is selected, the agent additionally produces an across-options recommendation naming the preferred direction, key tradeoffs, and what would change the recommendation.

### Labor rates

Effort is reported in hours and run-cost in token bands; no dollar rates live in the system, and the Director converts to dollars at the gate. A single blended rate may be added later — stored in an access-controlled file in the registry repository, maintained only by the Director — and only if buy-versus-build comparisons begin to need dollar-for-dollar figures against a license quote.

# 8. Approval Gates

There are four human gates plus one conditional sign-off. No override exists; the Director is already the decision on every request.

| Gate | Owner | Decides on | Decision |
| --- | --- | --- | --- |
| Requestor sign-off | Requestor | The captured request | Problem and acceptance criteria are correct |
| Gate 1a | Director | The costed short list | Pick 1 or more options for deep-dive, accept the triage recommendation directly, or send back for re-triage |
| Gate 1b | Director | The deep-dive | Approve the spend |
| Gate 2 | Director | The acceptance criteria | Accept the finished tool |
| R&D sign-off | R&D | Heavy / sensitive builds | Security approval (Director approves the handoff) |

**The one hard wall:** the security review and the R&D sign-off cannot be waived — by the Director or anyone else. Overriding a route is a judgment call the Director owns; overriding security is not on the table.

# 9. Build, QA & Security

## 9.1 Build avenues

"Build" is not one kind of artifact. Triage's classification selects the avenue, and the orchestrator routes to it by deterministic rule:

- **Code.** A script, integration, or small app. Built as source, run in the execution environment, QA'd by running it.
- **Agent-creation.** A prompt-defined agent (and pseudo-agents in the early period). "Build" means authoring and tuning the prompt and its tools; QA runs it against test cases.
- **Config-applied.** Settings or automations in a tool already owned. "Build" means applying the configuration to a staging instance; QA checks the configured behavior.
- **Config-instructions.** Used when no staging instance is reachable. The only output is a configuration guide for a human to execute. QA is a careful, reasoning-based correctness review, since there is nothing to run; the instructions ship flagged "unverified — validate on apply," and the acceptance criteria require the requestor to confirm it worked.

## 9.2 Execution environments

Environments are pluggable and selected at go-time by deterministic rule, by build type and modified by sensitivity and weight:

| Build type | Environment |
| --- | --- |
| Code | Ephemeral, sandboxed container (provisional lean), destroyed after the build |
| Config-applied | Staging instance of the target tool |
| Config-instructions | None — nothing executes |
| Agent / prompt | Prompt sandbox plus the test harness |

*Sensitive work gets stronger isolation; heavy work runs on R&D infrastructure. The ephemeral-container lean is recorded but not finally locked — the specific infrastructure is an R&D decision.*

## 9.3 Functional QA

Functional QA verifies that a build runs and meets its specification — functional scope only; security is explicitly out of scope. The QA mode varies by build type (a test harness for code and prompts, a staging instance for applied config, reasoning for instructions). QA is a separate agent from the build agent, on purpose: a builder grading its own work has a blind spot.

## 9.4 Security review

Two separate security agents review each build through different lenses — one for vulnerabilities (secure coding), one for data governance — kept separate so that one model does not anchor on the first risk it finds. They are backed by deterministic scanners (static analysis, dependency checks, and secret scanning) that run automatically in CI on the build's pull request before the agents, so the agents focus on the contextual issues scanners miss.

- Critical scanner or agent findings block the merge and escalate to the Director; lower-severity findings are advisory.
- If the two security agents disagree, the build is routed to the Director for review.
- Heavy or sensitive builds additionally take the R&D security sign-off.
- Coverage by type: code gets the full scanner set; config gets secret-scanning on any config-as-code plus the data-governance lens; prompt/agent builds get a prompt-injection and safety check in place of static analysis, with data governance still applying; instructions-only is pure agent review.

# 10. Agent Specifications

Ten agents run the workflow, plus the deterministic orchestrator. Each specification below is prompt-ready: precise enough that authoring the prompt afterward is near-mechanical, while remaining vendor-neutral. The sizing principle is constant:

*Spend frontier-model tokens only where judgment, code, or security justify it; use small models for capture, extraction, matching, and the ROM; keep control flow deterministic.*

## 10.1 Model sizing at a glance

| Tier | Profile | Agents |
| --- | --- | --- |
| Deterministic | Fixed rules, fully auditable, no token cost | Orchestrator (sequencing, routing, gating, logging) |
| Small (SLM) | Fast, cheap, narrow | Cost (ROM mode); Intake extraction pass; Registry maintenance (checking pass) |
| Mid LLM | Solid reasoning at lower cost | Intake (conversation); Stack-check; Functional QA; Portfolio (recommendation); Registry maintenance (descriptions) |
| Large / frontier | Strongest reasoning, code, and security judgment | Triage; Build; Functional QA (complex / instructions-only); Cost (deep-dive); Security – Vulnerabilities; Security – Data Governance |

## 10.2 Intake agent

| Field | Specification |
| --- | --- |
| **Trigger** | A team member opens a new tool request. |
| **Inputs** | The requestor's live messages; read access to connected systems for context where helpful. |
| **Task** | Conduct a live, adaptive interview; steer solution-talk back to the underlying problem; fill the intake output schema; draft acceptance criteria; obtain requestor sign-off. |
| **Outputs** | Persisted raw transcript; the structured request record (via the extraction pass); draft acceptance criteria; requestor sign-off. |
| **Tools / access** | Connected systems (read); invokes the small-model extraction pass after the conversation closes. |
| **Model** | Mid LLM for the conversation (runs live / streaming); SLM for the separate extraction pass. |
| **Decision authority** | None. Capture only — never decides, never blocks a request. |
| **Escalation / handoff** | On sign-off, hands the record and transcript to analysis. |
| **Guardrails** | Captures the problem, not a prescribed solution; the solution-idea field is optional and non-binding. |

## 10.3 Stack-check agent

| Field | Specification |
| --- | --- |
| **Trigger** | A signed-off intake record enters analysis. |
| **Inputs** | The structured request (especially the problem and current workaround); the capability registry. |
| **Task** | Determine whether existing tooling or agents already solve the problem, matching against capability statements filtered by support level and data-sensitivity. |
| **Outputs** | Matching capabilities with their support level, or a "no existing coverage" finding. Advisory to triage. |
| **Tools / access** | Registry (read, retrieval); connected systems of record (read) where needed. |
| **Model** | Mid LLM with retrieval over the registry. |
| **Decision authority** | None (advisory). |
| **Escalation / handoff** | Passes findings to triage, which runs next in the analysis sequence. |
| **Guardrails** | Only as accurate as the registry; never asserts coverage beyond what the registry supports. |

## 10.4 Triage / recommender agent

| Field | Specification |
| --- | --- |
| **Trigger** | Stack-check findings are available for a request. |
| **Inputs** | Structured request, transcript (for nuance), stack-check findings. ROM does NOT feed triage; ROM runs after triage and costs the option list triage produces. |
| **Task** | Run the six-outcome cascade and the build sub-decisions; produce a short list of 1–4 concrete, costable options plus a recommendation across them. The list is always produced — for route-elsewhere or don't-build recommendations, the list contains the notional option(s) that would have been considered, so the Director sees a consistent costed package at Gate 1a. |
| **Outputs** | A short list of 1–4 named options (each with route, label, summary, and route-specific fields), plus a recommendation (one of the six outcomes) with rationale. The orchestrator passes the list to ROM for costing, then both to Gate 1a. |
| **Tools / access** | Registry (read). Triage does not request ROM directly; the orchestrator runs ROM as the next sequential step after triage. |
| **Model** | Large / frontier — the highest-judgment reasoning in the system. |
| **Decision authority** | None — strictly advisory. Recommends; the Director decides. |
| **Escalation / handoff** | Delivers the package to Gate 1a. |
| **Guardrails** | Recommends only; never routes or blocks; honors the data-sensitivity overlay (raises guardrails, does not change the route). |

## 10.5 Cost agent (two modes)

| Field | Specification |
| --- | --- |
| **Trigger** | ROM mode — runs sequentially after triage on every request, costing the option list triage produced. Deep-dive mode — runs after Gate 1a on each option the Director selected for deep-dive (1 to N). |
| **Inputs** | ROM: the structured intake extract and triage's option short list (1–4 named options). Deep-dive: the structured intake extract, the raw intake transcript, the stack-check finding, the ROM output, and the list of options the Director selected at Gate 1a (1 to N). |
| **Task** | ROM: cost each option in triage's short list with effort, run-cost, license, and maintenance bands plus confidence and 2–3 key drivers per option. Deep-dive: produce a detailed breakdown per Director-selected option — phased effort, concrete dollar figures (web-sourced), maintenance forecast, assumptions, and risks; add an across-options recommendation when more than one option is selected. |
| **Outputs** | ROM: an array of costed options matching triage's list one-to-one. Deep-dive: an array of detailed option breakdowns matching the Director's selection one-to-one, plus an across-options recommendation when more than one was selected. |
| **Tools / access** | Web/tool access for current pricing (deep-dive); internal effort references; a blended rate if later introduced. |
| **Model** | SLM for ROM (deliberately cheap); mid-to-large LLM with tools for deep-dive. |
| **Decision authority** | None (advisory). |
| **Escalation / handoff** | ROM hands the costed list directly to Gate 1a (no return through triage). Deep-dive hands to Gate 1b. |
| **Guardrails** | ROM stays low-token and directional; bands only, no dollar figures (the Director converts at Gate 1a if needed). Deep-dive produces concrete dollar figures sourced from web pricing or the rate file if one exists; every dollar figure cites a source URL and retrieval date or is marked as an explicit assumption. |

## 10.6 Build agent

| Field | Specification |
| --- | --- |
| **Trigger** | The Director approves spend (Gate 1b) for a self-serve build. |
| **Inputs** | The approved option, acceptance criteria, build type. |
| **Task** | Build the tool to spec along the matching avenue (code / agent_creation / config_applied / config_instructions). |
| **Outputs** | The built artifact, committed to the GitHub backbone where applicable. |
| **Tools / access** | A pluggable execution environment selected at go-time; the GitHub repository. |
| **Model** | Large / frontier, coding-strong. |
| **Decision authority** | None over scope; builds to the approved spec. |
| **Escalation / handoff** | Heavy apps route to R&D rather than self-build; on completion, hands to functional QA. |
| **Guardrails** | Builds only what was approved; separate from QA — does not grade its own work. |

## 10.7 Functional QA agent

| Field | Specification |
| --- | --- |
| **Trigger** | A build completes. |
| **Inputs** | The built artifact, the acceptance criteria, build type. |
| **Task** | Verify it runs and meets the spec; functional only. QA mode varies by build type; instructions-only is a reasoning-based correctness review. |
| **Outputs** | Pass/fail against criteria, with findings; loops back to build on failure. |
| **Tools / access** | The execution environment and a test harness (code/prompt); a staging instance (applied config). |
| **Model** | Mid-to-large LLM with execution tooling; instructions-only uses the strong model (nothing to execute). |
| **Decision authority** | Decides functional pass/fail; not acceptance (that is the Director). |
| **Escalation / handoff** | On pass, hands to security review; on fail, returns to build. |
| **Guardrails** | Functional scope only — security is out of scope; a separate agent from build. |

## 10.8 Security agent — vulnerabilities

| Field | Specification |
| --- | --- |
| **Trigger** | Functional QA passes (for builds shipping code or touching data). |
| **Inputs** | The build's code and dependencies; deterministic scanner findings (SAST, SCA, secret scanning) from CI. |
| **Task** | Secure-coding review — injection, secrets, auth, unsafe calls — focused on contextual issues the scanners miss. |
| **Outputs** | Security findings with severity; pass/block. |
| **Tools / access** | Code (read); scanner outputs from CI. |
| **Model** | Large / frontier. |
| **Decision authority** | Can block on critical findings (escalates to the Director); part of the non-bypassable security wall. |
| **Escalation / handoff** | Disagreement with the data-governance agent routes to the Director; heavy/sensitive takes the R&D sign-off. |
| **Guardrails** | Cannot be waived by anyone, including the Director; backed by deterministic scanners. |

## 10.9 Security agent — data governance

| Field | Specification |
| --- | --- |
| **Trigger** | Same as the vulnerability agent. |
| **Inputs** | The build and its data flows; the request's data-sensitivity classification. |
| **Task** | Review data handling, access scope, isolation, and regulated-data rules against the governance standard. |
| **Outputs** | Governance findings; pass/block. |
| **Tools / access** | Code/config and data-flow context (read); the governance standard / checklist. |
| **Model** | Large / frontier. |
| **Decision authority** | Can block; non-bypassable, as with the vulnerability agent. |
| **Escalation / handoff** | Disagreement with the vulnerability agent routes to the Director; heavy/sensitive takes the R&D sign-off. |
| **Guardrails** | Fires on any sensitive-data touch regardless of build type, including config and prompt builds. |

## 10.10 Portfolio / pattern agent

| Field | Specification |
| --- | --- |
| **Trigger** | Scheduled daily, across the whole request corpus and the registry. |
| **Inputs** | All requests (open and historical); the registry. |
| **Task** | Cluster requests into themes via embeddings; for each theme, determine against the registry whether it is a build signal (no coverage) or an enablement signal (coverage exists but is unused); apply the tiered thresholds. |
| **Outputs** | A daily digest of themes with tier and signal type; pseudo-agent graduation flags. |
| **Tools / access** | Embeddings for clustering; the registry and request corpus (read). |
| **Model** | Embeddings plus a mid LLM for the recommendation. Batch, latency-insensitive, low-cost. |
| **Decision authority** | None (advisory to the Director). |
| **Escalation / handoff** | Surfaces recommendations to the Director; feeds reuse awareness back to stack-check and triage. |
| **Guardrails** | A count against existing coverage flips meaning (build vs. enablement); thresholds are tunable. |

## 10.11 Registry maintenance agent

| Field | Specification |
| --- | --- |
| **Trigger** | Scheduled daily, or on demand when a process or tool changes. |
| **Inputs** | GitHub (built artifacts); the SSO/app-catalogue (SaaS inventory); the current registry. |
| **Task** | Keep the registry current — verify entries against their sources, stamp last-verified, and propose updates. |
| **Outputs** | Auto-merged factual updates; pull requests for judgment items (capability statements, clearances, graduation). |
| **Tools / access** | GitHub API; SSO/app-catalogue API; writes to the registry repo via pull request. |
| **Model** | SLM for the checking pass; mid LLM when proposing description updates. Batch. |
| **Decision authority** | Auto-merges machine-verifiable facts; everything judgment-bearing waits for the Director's PR approval. |
| **Escalation / handoff** | Opens pull requests to the Director (registry owner). |
| **Guardrails** | Never silently changes judgment fields; the last-verified stamp is the visible freshness signal. |

# 11. Provider Strategy

The provider-neutral seam is realized by adopting an AI gateway rather than building one: a unified endpoint that routes calls across model providers, so switching or adding a provider becomes a configuration change rather than application code. By the workflow's own triage logic, the seam is a generic, well-served capability — a buy, not a build.

### Sequencing

- Build the neutral seam (adopt a gateway) from day one, with multi-provider capability wired in.
- Operate single-provider to start, on one model family, for simplicity of governance, billing, and security posture.
- Go multi-provider per agent later, only where usage data proves it pays — the cheap high-volume agents (extraction, ROM) for cost, and the specialists (build, security) for capability.

### Development & test setup (recorded)

For testing now: OpenRouter with bring-your-own-key (the team's own provider key), cross-provider fallback disabled so a failed call never silently falls back to a pooled provider, a $50/month spend cap with "include BYOK in limit" enabled so the cap measures real model usage, and the same cap mirrored on the provider side as the true backstop. This is dev/test only, with synthetic or sanitized data — the hosted gateway is not fit for production or real customer data.

### Production

Before any real data flows, OpenRouter is replaced by a self-hostable or otherwise compliant gateway. Selection is driven first by deployment model (self-host / VPC) and data-governance terms — a data processing agreement, a no-training commitment, retention or zero-retention options, and compliant hosting (plus a business-associate agreement if health data is ever in scope) — and only second by provider breadth. The specific production gateway is an open decision.

# 12. The Capability Registry

The registry is the single source of truth for what tooling and agents exist and what each can do. It powers the stack-check and the reuse-before-rebuild loop. Without it, the stack-check is guessing.

| Property | Decision |
| --- | --- |
| Scope | The Director's team only. |
| Owner | The Director, sitting above the agents. |
| Backbone | A single private, access-controlled GitHub repository. |
| Format | One record per file in YAML (diff-friendly), foldered by record type. |
| Change model | Every change flows through a pull request, giving a built-in review and audit trail. |
| Record types | Tool; Agent (built by the workflow); Pseudo-Agent (transitional Claude Projects acting as agents). |
| Granularity | Hybrid — top-level record per tool/agent, with nested, tagged capability statements. |

### Hybrid granularity

The tool, agent, or pseudo-agent is the top-level record. Beneath it sits a structured list of capability statements, each a short, problem-shaped phrase tagged with a support level (native / configurable / not supported) and a data-sensitivity clearance. Matching happens at the statement level (precise); maintenance and freshness happen at the record level (manageable). The registry is grown demand-driven — by the capabilities people actually request and the recurring themes the portfolio agent surfaces — not enumerated exhaustively.

### Freshness

The registry maintenance agent runs daily. It auto-merges machine-verifiable facts (a tool appeared or vanished, an API changed, a license lapsed, the last-verified stamp) and opens a pull request for the Director's approval on anything requiring judgment (capability statements, data clearances, pseudo-agent graduation). The last-verified date is the honesty signal: a stale date flags a record that has not been confirmed recently.

### Inventory sources

- **GitHub** auto-discovers everything the workflow builds, and hosts the registry itself.
- **An SSO / app-catalogue integration** pulls the SaaS-tool slice — existence and metadata only; capability statements stay human-authored, because a catalogue does not know what a tool is good for in problem terms.
- **Pseudo-agents** are registered manually, since they are invisible to both GitHub and SSO — but they still live in the same registry, so everything is in one place to be scanned.

The full schema is in Appendix C.

# 13. Deployment, Lifecycle & Portfolio Monitoring

### Deployment & hand-off

On acceptance at Gate 2, the tool is deployed, assigned an owner and a review/sunset date, logged, and registered. Registration closes the reuse loop: the next request that needs the same thing is matched to it by the stack-check and reused instead of rebuilt, and the portfolio agent sees the cluster forming.

### Pseudo-agent graduation

The portfolio agent watches pseudo-agent usage and flags when one is doing enough real work to deserve being rebuilt as a first-class tool. That flag is the build-out path, surfaced automatically rather than tracked by hand.

### Recurring-theme thresholds

The portfolio agent applies tiered thresholds to each cluster, and reads the count against the registry — whether existing coverage exists changes what the count means:

| Matches | Tier | Action |
| --- | --- | --- |
| 1–2 | Noise floor | Tracked, not surfaced. |
| 3–5 | Worth review | Appears in the daily digest for consideration. |
| 6–9 | Likely candidate | Surfaced with a recommendation to provide a shared tool. |
| 10+ | Desperate need | Flagged as priority. |

*Build vs. enablement signal: matches with no existing coverage are a build signal; matches where a tool or agent already covers the theme are an enablement signal — an adoption or awareness gap, not a build need.*

# 14. Prerequisites, Dependencies & Governance

### Dependencies

- **The capability registry** — the single largest dependency; the stack-check and reuse loop both lean on it.
- **The AI gateway** — the provider-neutral layer through which all model calls route.
- **The GitHub backbone** — a private repository for built artifacts and the registry, with CI for scanning. Because GitHub-native scanning is used rather than a platform with it built in, the scanner layer is wired up explicitly as a build task.

### What is logged

Every gate decision, the full decision trail (there is no override path to obscure it), all security findings, and every registry pull request. The audit trail and governance live in the application and the registry — not in the gateway, which is only a router.

### Data governance

- Provider terms are gated on a data processing agreement, a no-training commitment, and retention or zero-retention options before any real data is sent.
- Any request touching customer, financial, or regulated data forces the security review, and heavy-plus-sensitive work additionally takes the R&D sign-off.
- Development and testing use synthetic or sanitized data only; real data waits for the compliant production gateway.

# 15. Open Decisions

Deliberately deferred; none blocks the design. Each is recorded here so it is decided on purpose rather than by default.

- Which production-grade compliant gateway to adopt, and on what data-governance terms.
- Which additional model providers to add per agent, and when — a data-driven call once usage is observed.
- The specific build-environment infrastructure (with R&D); the ephemeral-container lean is recorded but not finally locked.
- The specific scanner tool selection and CI plumbing (with R&D).
- The registry inventory-source integration specifics — which SSO / app-catalogue, and its API.
- Whether and when to add a cheap pre-intake out-of-scope classifier, data-driven via the portfolio agent's clustering of route-elsewhere outcomes. v1 routes everything through intake; if route-elsewhere recurs frequently, that's the signal to add a pre-intake filter.
- Whether and when to introduce a blended labor rate for dollar-denominated cost output.
- Tuning of the recurring-theme thresholds, which are set initially and refined with data.

# Appendix A — Intake Output Schema

The structured record the intake agent must walk away with. Auto-filled fields are populated by the system; the rest come from the conversation. The transcript persists separately as the durable record.

| Field | Description |
| --- | --- |
| Requestor / team / date | Auto-filled from identity and timestamp. |
| Request title | A short working name for the request. |
| Problem / outcome | What the requestor is trying to achieve — the problem, not a prescribed tool. |
| Current workaround | How they handle it today; the highest-signal field for the stack-check. |
| Success criteria | What "good" looks like; seeds the acceptance criteria. |
| Frequency | How often the need arises. |
| Who is affected | Just the requestor, the team, multiple teams, or customers. |
| Time cost | Effort the problem consumes, for sizing and prioritization. |
| Deadline | Any date constraint, if present. |
| Systems involved | Which systems the need touches; feeds the stack-check. |
| Data sensitivity | None / internal / customer / financial / regulated; routes the security guardrails. |
| Customer-facing | Whether the output is customer-facing. |
| Solution idea (optional) | The requestor's idea, explicitly non-binding. |
| Attachments | Any examples, links, or files. |
| Context / constraints / nuance | Free-text capture of relevant detail that does not fit a field, so context is not lost. |
| Acceptance criteria | Drafted by the agent, approved by the requestor at sign-off. |
| Transcript reference | Pointer to the persisted raw conversation. |

# Appendix B — Triage Heuristics

The logic behind each node of the six-outcome cascade. The order is intentional — cheapest, highest-volume filters first.

### Belongs to another function?

Before annualizing impact or matching against the registry, ask whether the request is a tooling/software/AI matter at all. Common out-of-scope categories: IT support (hardware, network, account access), HR (people, policy), facilities (workspace, building), and incident-style security or compliance asks that belong to those teams' own intake processes. Tells: the requestor describes a personal or operational problem with no tool dimension; the systems involved are infrastructure rather than business applications; the requestor explicitly asks for a person rather than a tool. Where this resolves, route elsewhere with the owning team named — the recommendation is suggestive, never automatic, and the Director approves it at Gate 1a like any other outcome.

### Worth solving?

Annualize the impact: frequency × people affected × time per occurrence, weighed against a rough build-plus-maintenance floor. The bar is whether the recurring cost clears the floor, not whether the task is annoying. Trivial, one-off, or single-person low-cost needs route to don't-build with the rationale stated.

### Does a tool we own fit?

Match the problem and the current workaround against the registry's capability statements. If an owned tool can do it natively or with configuration, route to configure. The workaround field is the tell: "I do this by hand" often means the tool already does it and no one enabled it.

### Is it a process or training gap?

If the real problem is that people do not know an existing capability exists, or a process step is missing or broken, no software fixes it. Route to a process or training fix — distinct from configuring a tool.

### Does buying beat building?

Lean buy when the capability is generic and well-served by the market, when building and maintaining it would be costly or risky, when it needs vendor support, or when a vetted vendor lowers regulated-data risk. Lean build when the need is bespoke and tightly coupled to the stack, when it is cheap to build with existing capability, or when there is no good market option. The ROM arbitrates: if a build estimate dwarfs a license for an equivalent tool, that is a buy signal.

### Build sub-decisions

Light vs. heavy determines the lane (self-serve vs. R&D); customer-facing or sensitive work can force heavy even when small. AI vs. deterministic picks the engine — judgment and language call for a model, rules and structure call for deterministic automation — and is the largest input to run-cost.

### Data-sensitivity overlay

Orthogonal to the route. Sensitivity does not pick the outcome; it raises the guardrails on whatever is built — forcing the security review and, for heavy-plus-sensitive work, the R&D sign-off.

### Producing the costable short list

Once the cascade has resolved (or in parallel with the final routing decision), triage assembles its short list of 1–4 options. Each option is named concretely enough that ROM can cost it:

- **Configure options** cite the registry record and capability statement. If stack-check returned a native or configurable match, that match becomes a configure option; the option's label and summary describe what configuration is involved.
- **Build options** specify the avenue (code / agent_creation / config_applied / config_instructions), the engine (ai / deterministic), and the weight (light / heavy). These are the same sub-decisions described above; they are recorded *on the option* so the option is fully specified.
- **Buy options** name the vendor or, where no specific vendor is yet identified, the vendor category and the capability being acquired.

When the resolved outcome is route-elsewhere or don't-build, triage still produces a short list — the notional option(s) that would have been pursued if the workflow had taken the request — and the recommendation captures the route-elsewhere/don't-build rationale. ROM costs the notional list so the Director sees a consistent analysis package at Gate 1a, including the cost of the alternative the recommendation is steering away from.

Where genuine alternatives exceed four, triage selects the four it judges most informative to the Director's decision and notes any dropped alternatives in the recommendation rationale.

# Appendix C — Registry Schema Reference

### Shared core (every record)

| Field | Description |
| --- | --- |
| id | Stable slug; never reused. |
| name | Display name. |
| type | Tool / Agent / Pseudo-Agent. |
| category | From the category vocabulary. |
| status | Planned / In build / In pilot / In use / Deprecated. |
| owner | Accountable role or person. |
| data_cleared_for | One or more sensitivity levels. |
| discovery | Auto-GitHub / Auto-SSO / Manual. |
| last_verified | Date stamped by the maintenance agent. |
| capabilities | List of capability statements (below). |
| notes | Free text. |

### Capability statement (nested, identical across all types)

| Field | Description |
| --- | --- |
| id | Short reference, so agents can match and cite a specific capability. |
| statement | A short, problem-shaped phrase, matchable to a request rather than a marketing feature. |
| support | native / configurable / not_supported — the hinge into the triage tree. |
| data_sensitivity | Clearance for this specific capability. |

### Type-specific fields

| Type | Fields |
| --- | --- |
| Tool | cost_basis; integrations (APIs / connection points); admin. |
| Agent | origin = built-via-workflow; built_date; source_ref (repo path); model_tier; run_cost (token band). |
| Pseudo-Agent | origin = Claude Project; transitional = true; graduation_candidate (set by the portfolio agent); replaced_by (optional). |

### Controlled vocabularies

| Vocabulary | Values |
| --- | --- |
| type | Tool / Agent / Pseudo-Agent |
| status | Planned / In build / In pilot / In use / Deprecated |
| support | native / configurable / not_supported |
| sensitivity | None / Internal / Customer / Financial / Regulated |
| discovery | Auto-GitHub / Auto-SSO / Manual |
| cost_basis | per-seat / usage / flat / free |
| model_tier | SLM / mid / large/frontier |
| category | Work management / CRM / Finance / Comms / Data/analytics / Dev/engineering (grows demand-driven, each addition an approved PR) |

# Revision History

Newest entry at the top.

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 0.3 | 06/29/2026 | Director | Sequenced the analysis stage (stack-check → triage → ROM → Gate 1a); redefined triage's output as a costable short list of 1–4 named options always produced; extended Gate 1a to allow picking 1 or more options into deep-dive; generalized deep-dive to N options with an across-options recommendation when N > 1. Normalized the build-avenue and engine enum tokens (code / agent_creation / config_applied / config_instructions; ai / deterministic) to match the agent contracts. |
| 0.2 | 06/26/2026 | Director | Added "Route elsewhere" as a sixth, advisory triage outcome (§6, §10.4, Appendix B); recorded a new open decision for a potential pre-intake classifier (§15). |
| 0.1 | 06/25/2026 | Director | Initial draft capturing the architecture and process design end to end. |
