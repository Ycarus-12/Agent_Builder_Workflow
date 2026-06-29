# CLAUDE.md — Agentic Tool-Request Workflow (Build)

You are the build engineer for an internal, agent-led tool-request workflow. The design
phase is **complete and frozen**. Your job is to CODE the application from a finalized
spec set — not to redesign it. The Director is the sole decision authority: propose and
flag; the Director decides. Surface risks and better approaches proactively, but never
silently reopen a locked decision — if a new idea conflicts with one, flag it explicitly.

## Read these first, in this order (source of truth)

1. `docs/context_06_29.md` — current state, locked decisions, canonical vocabulary (§5), build order (§9). Start here.
2. `docs/Agentic_Tool-Request_Workflow_Architecture_v0_3.md` — the end-to-end design. Registry SCHEMA is **Appendix C**; intake schema is **Appendix A**. (A `.docx` of the same content sits beside it for human reading; use the `.md`.)
3. `docs/orchestrator-contract_v1_1.md` — the deterministic application contract: state machine (§2), input envelope + context-attachment rules (§3), validate-and-retry (§5), sensitivity overlay (§6), eval harness (§7), logging (§8). Primary build spec for the orchestrator.
4. `agents/` — the 12 agent prompts you'll wire in. `evals/` — the 9 eval suites that gate them. Treat each eval suite's JSON schema as the agent's output contract.

Before creating anything, check what already exists so you don't collide with prior work.

## Recorded tool decisions (confirm before building)

The design is tool-agnostic; these bind the seams to concrete tools:

- **GitHub** — the capability registry repo (one YAML record per file, PR-based audit trail); built-artifact repos; CI (GitHub Actions) running the eval harness as a merge gate and the security scanners.
- **Posit Connect (Cloud)** — hosting/deploy target for the orchestrator service and the Director gate UI; the "deploy & register" target for built tools.
- **Resend** — all outbound email: gate-decision prompts to the Director, route-elsewhere hand-offs, requestor sign-off and acceptance notices.
- **Airtable** — the application's operational datastore: request records, pipeline state, gate decisions, audit log. **NOT the registry** (the registry stays GitHub-YAML). **Confirm this role with the Director before building against it.**
- **Model access** — all model calls route through the provider-neutral gateway seam. Dev/test: OpenRouter + BYOK (team Anthropic key), cross-provider fallback disabled, $50/mo cap. Operate single-provider (Anthropic) to start; do **not** hardwire a provider into application code — keep the seam.
- **Language** — **Python** (FastAPI for the orchestrator/API). Locked: the team builds in Python.

## Non-negotiables (locked — do not reopen)

- The orchestrator is DETERMINISTIC code (sequencing, routing, gating, logging). No model judgment in the plumbing. Judgment lives only in agents.
- The Director is the only decision authority. Gates 1a/1b/2 and the R&D security sign-off are the only stop points. Security review is non-bypassable, including by the Director.
- Structured agent outputs use constrained decoding + schema validation + bounded retry (default 3). On exhaustion, escalate to the Director — never silently fall back to a bigger model.
- Implement the canonical enums (context §5) VERBATIM: `route`, `outcome`, `build_type`/`avenue`, `engine`, `weight`, `data_sensitivity`, `support`, `status`, the sign-off marker `[[INTAKE_SIGNOFF_CONFIRMED]]`.
- `unspecified` data sensitivity is treated as sensitive-until-confirmed.
- No secrets in code — use environment variables / Connect managed variables.
- Every agent call logs prompt version + commit hash for traceability.

## Build order (context §9) — one phase at a time

1. **Registry repository** — GitHub repo, YAML schema from Architecture Appendix C, foldered by record type. Largest dependency (stack-check, triage, portfolio, registry-maintenance all read it). Build first.
2. **Orchestrator spine** — the state machine and agent-invocation contract from `orchestrator-contract_v1_1.md`.
3. **One agent end-to-end** — wire intake (conversation + extraction) through the gateway; produce a real structured record; persist the transcript. Prove the loop.
4. **Eval harness in CI** — implement the harness (orchestrator-contract §7); wire each eval suite as a GitHub Actions merge gate.
5. **Remaining agents** — stack-check → triage → ROM → deep-dive → build → QA → security → portfolio → registry-maintenance, each behind its eval gate.

Deferred (do NOT block the spine; flag when reached): build-agent execution environment, scanner tooling selection, production gateway selection.

## Working rules

- **Outline before building.** For any phase or significant deliverable, propose the structure and WAIT for the Director's approval before writing it.
- Lead with the bottom line; flag risks, gaps, and better approaches proactively.
- When ambiguous, state your assumption explicitly and proceed; don't stall.

## First task — do this, then stop for approval

1. Confirm the tool-role mapping above (especially Airtable's role as the app datastore, not the registry).
2. Read the source-of-truth set and restate, briefly and in your own words, the registry schema (Appendix C) and the orchestrator state machine (§2) so we know they landed.
3. Propose a concrete Phase 1 plan (registry repo): repo structure, the YAML record + capability-statement schema as files, folder layout by record type, the PR workflow, and 2–3 seed records.
4. Outline it and WAIT for approval before writing the repo.
