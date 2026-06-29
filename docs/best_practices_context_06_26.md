# PART 3 — PROMPT-AUTHORING BEST PRACTICES (REFERENCE)

> **Purpose.** Standing reference for the prompt-authoring workstream. It defines the canonical prompt template every agent inherits, the tier-specific conventions, and the sourced rationale behind each choice. Use it when authoring the ten Section 10 agents, starting with intake.
>
> **Status:** Reference · **Date:** 06/25/2026 · **Owner:** Director
> **Relationship to project:** Companion to the *Architecture & Process Specification (v0.1)* and the *Project Context Export*. This document governs *how* prompts are written; the Architecture doc governs *what* each agent does.
>
> **Provider scoping (locked):** mid/high-tier agents run on Anthropic (Claude) — Anthropic-specific conventions apply. Low-tier / SLM agents are provider-agnostic — provider-neutral conventions apply. The template body stays unbranded; model/tier is metadata on the artifact, never hard-wired into the prompt text.

---

## 1. Bottom line

- **Keep the eight-section template, but reorder and rename it.** Lead with Identity → Operating context → Task & success criteria, then Inputs → Output contract → Tools → Guardrails → Examples → metadata footer. This front-loads the high-signal framing and matches current Anthropic guidance to organize prompts into clearly delimited sections.
- **Fork the template into two tier variants.** A **frontier (Claude) variant** (XML tags, explicit instructions, adaptive thinking, structured outputs, no prefill) and an **SLM variant** (labeled blocks, 1–2 compact few-shots, one enforced output format, hard token budgets, decision rubrics, validator + retry).
- **Make every prompt eval-first and version-controlled.** Each agent ships with test cases / acceptance criteria and a machine-checkable output schema; prompts live in Git as immutable, semantically versioned artifacts with metadata headers, because a deterministic orchestrator parses their outputs.

---

## 2. The canonical prompt template

Recommended section order, with what each holds and why. All ten agents inherit this structure; the only thing that varies by agent is the content and the tier variant (Section 3).

**Order:** Identity & role → Operating context → Task & success criteria → Trigger & inputs → Output contract → Tools & access → Guardrails & boundaries → Examples → Metadata footer.

1. **Identity & role.** Functional name, one-line mission, position in the pipeline (what hands to it, what it hands onward). A single role sentence measurably focuses tone and behavior. Anthropic's framing is to treat the model like a capable new hire who lacks your context — the more precisely you specify what you want, the better the output. *(Anthropic — Prompting best practices.)*

2. **Operating context.** State that the agent sits in an advisory, human-gated pipeline; that it is **stateless and receives context per call**; and that a deterministic orchestrator owns routing, gating, and logging. The governing principle is to supply the smallest possible set of high-signal tokens for the outcome. Two practical conventions follow: place long-form data near the **top** of the prompt and the instruction/question at the **end** (Anthropic reports query-at-the-end can improve quality materially on multi-document inputs, consistent with the documented "lost in the middle" U-curve where mid-context information is recalled worst); and reference large artifacts **just-in-time** (paths / IDs / stored queries) rather than dumping them inline. This is the right model for attaching different artifacts to different agents — e.g., transcript to judgment stages, structured extract to mechanical stages. *(Anthropic — Effective context engineering for AI agents; Liu et al., 2024, "Lost in the Middle.")*

3. **Task & success criteria.** The core instructions, written at the **right altitude** — between brittle hard-coded logic and vague high-level guidance. Use sequential numbered steps where order or completeness matters. Fold acceptance criteria in here so the prompt is testable from day one: a good task is one where two domain experts would independently reach the same pass/fail verdict. *(Anthropic — Effective context engineering; Anthropic — Demystifying evals.)*

4. **Trigger & inputs.** What fires the agent and the exact input schema, including which artifacts are attached and their format. **Isolate input data from instructions with delimiters / XML tags** — this stops the model from blending supplied content into its instructions and is one of the highest-leverage reliability habits for structured tasks.

5. **Output contract.** The exact shape of what the agent produces and its handoff target. For orchestrator-parsed agents, specify a JSON/structured schema and enforce it with **constrained decoding** (structured outputs / strict tool use), layered with schema validation and a retry loop. Phrase format requirements **positively** (say what to produce, not what to avoid). For advisory agents feeding a human, structure the output *for a decision*: recommendation, rationale, risks, and an explicit uncertainty note. *(Anthropic — Prompting best practices; Anthropic — Structured outputs.)*

6. **Tools & access.** Describe each tool precisely; keep a **minimal, non-overlapping** set; give explicit when-to-use *and* when-NOT-to-use guidance; return token-efficient results (pagination / filtering / truncation defaults). Anthropic frames a tool as a contract between deterministic systems and non-deterministic agents, and offers a useful test: if a human engineer can't say definitively which tool applies in a situation, the agent won't either. On the newest Claude models, **soften aggressive trigger language** ("CRITICAL: you MUST…", blanket "always use X") — it causes tool over-triggering; use plain "Use this tool when…" phrasing. *(Anthropic — Writing effective tools for AI agents.)*

7. **Guardrails & boundaries.** Hard rules, decision-authority limits, and the do-not-do list. Allow the model to say "I don't know"; restrict it to provided context where appropriate; require grounding/quotes for factual work over long inputs; phrase rules positively. **Keep guardrails minimal** — excessive constraint and leak-proofing adds complexity that can degrade the rest of the task. (For this pipeline, the never-decide / never-block constraint belongs here, stated plainly.)

8. **Examples.** 3–5 diverse, canonical few-shots wrapped in `<example>` tags (grouped in `<examples>`); not a laundry list of edge cases. Newer Claude models attend closely to examples, so each must model exactly the behavior you want and avoid patterns you don't. For SLMs, use 1–2 compact, format-conformant exemplars (Instruction → exemplar → new input).

9. **Metadata footer.** Version, owner, target model/tier, and changelog reference — supporting cross-prompt consistency in Git and runtime traceability. Kept out of the prompt's behavioral body.

> **Note on the original draft template.** All eight original sections survive. The changes are: reorder to front-load Identity/Context/Task; rename "Task" to "Task & success criteria" (folding criteria in); move Examples to last; add the metadata footer. Anthropic notes exact formatting matters less as models improve, but structure is retained because it aids deterministic parsing and weaker models.

---

## 3. Tier-specific conventions

### 3a. Mid / high tier — Anthropic (Claude)

- **XML tags as section boundaries** — consistent, descriptive names; nest for hierarchy. There is no canonical "best" tag set; the value is removing ambiguity between instructions, context, examples, and data.
- **Explicit instructions.** Newer Claude models do what is asked and no more; request "above and beyond" behavior explicitly. Soften over-prompting on the latest models to avoid over-triggering.
- **Adaptive thinking** on the newest models (the model decides when and how much to think); tune via the effort parameter. Anthropic reports adaptive thinking outperforms fixed extended-thinking budgets for agentic, multi-step work. Extended thinking with a token budget still functions but is the older pattern.
- **No prefill on the newest Claude models** — prefilling the assistant turn now returns a 400 on current Opus/Sonnet (and the newer Fable/Mythos lines). This **reverses** older guidance that recommended prefilling `{` to force JSON. Migrate to structured outputs or explicit formatting instructions.
- **Structured outputs** (JSON-schema + strict tool use) for schema-guaranteed parsing into the orchestrator. Practical constraints: flatten recursive schemas, set `additionalProperties: false`, allow generous `max_tokens`; not compatible with citations or with JSON-mode prefilling.
- **Long context:** data at top, query at end, ground answers in quotes for large inputs.

### 3b. Low tier — provider-agnostic (SLM)

Small models map cleanly to the pipeline's capture / extraction / matching / ROM-cost roles. Provider-neutral conventions:

- **One enforced output format.** Do not ask an SLM to juggle JSON/XML/YAML — pick one and hold it. Format drift is the characteristic small-model failure.
- **Short, explicit prompts with labeled blocks** (`[Context]`, `[Task]`, `[Output]`); 1–2 short exemplars; **hard token budgets** ("Target 120–180 tokens; never exceed 220"); **decision rubrics** that force a single choice; pass only the 1–3 most relevant context snippets; split multi-hop instructions into numbered steps; require "not found in sources" instead of guessing.
- **Always wrap with a format validator + retry**, and decompose tasks so each step is easy for a small model.
- **Escalate, don't force.** Where a subtask exceeds the small model, fall back to a larger model for that step (heterogeneous-by-design). This is the prompt-side correlate of the tiered model strategy already locked in the architecture.

> *Source note: SLM strategy draws on NVIDIA Research, "Small Language Models are the Future of Agentic AI" (arXiv:2506.02153) — an explicitly self-described position/value statement, not an independent benchmark. Use it for direction, not as measured fact (see Caveats).*

---

## 4. Multi-agent handoffs & advisory output

- **Four-part handoff contract — make these required fields in every agent spec.** Anthropic's multi-agent guidance requires each agent to be given four things: an **objective**, an **output format**, **guidance on which tools/sources** to use, and **clear task boundaries**. Without detailed task descriptions, agents duplicate each other's work, leave gaps, or fail to retrieve what's needed. Anthropic also scales effort to task size to avoid over-spawning. *(Anthropic — How we built our multi-agent research system.)*
- **Advisory output is shaped for a decision.** Standardize the advisory agents (stack-check, triage, cost, portfolio) on a structured `recommendation / rationale / risks / uncertainty` shape so the Director gets a consistent decision surface at the gates.
- **Treat model confidence as a signal, not a gate.** LLM self-reported confidence is poorly calibrated (claimed high confidence routinely overstates real accuracy), and miscalibration **compounds across a chain** — which is a quantitative argument *for* the explicit human gates already in the design, not a reason to automate them away. Gate on **risk tier and business rules**, not on a model's stated confidence.
- **Prompt-side mitigations for chain failure modes:** explicit boundaries to stop duplication; "stop when you have sufficient results" to curb over-searching; externalize plans/state before context fills.

---

## 5. Conversation vs. extraction agents (the intake split)

The locked intake split (capable conversation model + cheap extraction pass) is exactly the right shape; author the two halves differently:

- **Conversation / intake agent** — stateful, streaming, multi-turn. Needs **escalation criteria** (when to hand to a human), tone, and turn-management guidance in the prompt. Pattern: a session-based, multi-turn client.
- **Extraction agent** — single-pass, mechanical, schema-locked; no conversational preamble or verbal summary. An ideal SLM candidate with constrained decoding. Pattern: a single-shot call that forces the structured-output tool exactly once.

---

## 6. Structured output & the orchestrator contract

For every agent whose output the deterministic orchestrator parses:

- **Use constrained decoding** (structured outputs / strict tool use with forced tool choice) — it compiles the schema into a grammar and restricts generation, giving near-guaranteed schema conformance.
- **Layer defense:** schema validation on receipt + a bounded retry loop.
- **Do not rely on prefill** on the newest Claude models (returns 400). Reserve free-form prose for the human-facing advisory output only.

---

## 7. Versioning & maintainability (ten prompts as Git artifacts)

- **Immutable, semantically versioned** prompts: once a version is cut, it is never edited in place. Major = structural overhaul, minor = new capability/criteria, patch = typo/tweak.
- **Metadata header per prompt** (version, author, date, purpose, target model/tier, dependencies) + a **CHANGELOG**.
- **Log the prompt version / commit hash with each run** so orchestrator traces link back to the exact prompt — essential for debugging regressions when a deterministic system parses outputs.
- **Shared template + per-tier variant** keeps the ten consistent; a shared eval harness with a universal rubric scores all agents on the same criteria.

---

## 8. Rollout sequence

1. **Restructure** the template to the Section 2 order; convert any "CRITICAL/MUST/if-in-doubt" language to plain phrasing.
2. **Fork** into the frontier (Claude) and SLM variants (Section 3).
3. **Make each agent eval-first** — 5–10 representative test cases + a machine-checkable schema before finalizing; concrete 1–5 rubric anchors for advisory agents.
4. **Lock the contracts** — four-part handoff fields required; constrained decoding for all orchestrator-parsed outputs; standardized advisory shape.
5. **Operationalize in Git** — semver, immutable releases, metadata headers, changelog, commit-hash logging.

---

## 9. Thresholds that should trigger a change in approach

- Frontier model over-triggers tools or over-thinks → soften language and/or lower effort.
- SLM fails schema conformance in evals → add constrained decoding + retry, or escalate that subtask to a larger model.
- Advisory confidence proves miscalibrated in review → drop confidence-gating in favor of risk-tier/business-rule gating.
- A prompt edit regresses eval scores → block the merge (treat evals like unit tests in CI).

---

## 10. Caveats & source-reliability notes

- **Model-version specifics need confirmation at authoring time.** Several findings reference specific Claude versions and the prefill-deprecation list. Treat them as the live state of Anthropic's docs as of this research; confirm exact per-version behavior (adaptive-thinking defaults, prefill support, structured-output constraints) against `docs.claude.com` / `platform.claude.com` when you write each prompt.
- **The NVIDIA SLM paper is a position/value statement authored by NVIDIA**, not an independent empirical study; its cost figures cite secondary sources and its exemplar models skew toward NVIDIA. Use it for directional, provider-neutral SLM strategy only.
- **Formatting rigor is becoming less critical as models improve** (Anthropic's own note). For the strongest Claude models, heavy XML/prescriptive sectioning may be optional — but it is retained here because it aids deterministic parsing and helps the SLM tier.
- **Primary sources were weighted as authoritative.** Where official Anthropic/NVIDIA material existed it was used directly; practitioner sources were used only to corroborate.

---

## Sources

- Anthropic — *Effective context engineering for AI agents.* https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — *Writing effective tools for AI agents.* https://www.anthropic.com/engineering/writing-tools-for-agents
- Anthropic — *How we built our multi-agent research system.* https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic / Claude Platform Docs — *Prompting best practices.* https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Claude Platform Docs — *Using the Messages API.* https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- NVIDIA Research (Belcak et al.) — *Small Language Models are the Future of Agentic AI*, arXiv:2506.02153. https://arxiv.org/abs/2506.02153
- Emergent Minds — *Context Stops Being Scarce* (long-context practitioner analysis). https://paddo.dev/blog/million-token-context/
- Referenced by name (confirm at authoring time, no fixed URL captured here): Anthropic *Structured outputs* announcement and *Migration guide* (prefill deprecation); Anthropic *Demystifying evals for AI agents*; Liu et al. (2024), *Lost in the Middle*; Simon Willison's analysis of Claude system prompts.

---

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | 06/25/2026 | Director | Initial reference capturing 2026 prompt-authoring best practices and the canonical agent prompt template. |