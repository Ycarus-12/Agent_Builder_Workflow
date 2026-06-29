---
artifact: security-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Combined eval scaffold for the two security agents. Covers
  security-vulnerabilities v1.0.0 (contextual secure-coding review) and
  security-governance v1.0.0 (data governance, access scope, regulated-data
  rules). Includes schema validation cases, per-agent substantive cases,
  disagreement-detection cases, hard-fail pattern detection, and the CI rules.
  Same one-file pattern used by prior combined evals (intake-evals,
  cost-estimation-evals).
covers:
  - security-vulnerabilities v1.0.0
  - security-governance v1.0.0
dependencies:
  - Prompt-Authoring Best Practices §3 (eval-first), §6 (orchestrator contract)
  - orchestrator-contract v1.1.0 §7 (eval harness shape)
  - Architecture & Process Specification v0.3 §9.4 (Security review),
    §10.8 (Vulnerabilities agent), §10.9 (Governance agent)
changelog: v1.0.0 initial scaffold.
---

# Security Agents: Eval Scaffold (v1.0.0)

This scaffold covers both security agents. Both agents produce structured
findings arrays; both are machine-checkable for schema and field rules. The
judgment content (finding specificity, recommendation quality, human_summary
usefulness) is rubric-scored. Disagreement-detection cases exercise the
orchestrator's ability to derive effective verdicts from the findings arrays
and detect a split.

The harness runs schema validation cases and hard-fail detection on every
commit. Substantive cases run on a schedule and on every PR touching either
security agent prompt.

---

## PART A -- Schema validation

### A.1 Machine-checkable output contract: security-vulnerabilities

Every vulnerability agent output must validate against this schema. **Pass =
validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SecurityVulnerabilitiesOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["request_title", "build_type", "findings", "human_summary"],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "build_type": {
      "type": "string",
      "enum": ["code", "agent_creation", "config_applied",
               "config_instructions"]
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "finding_id", "severity", "category", "description",
          "location", "recommendation", "scanner_covered"
        ],
        "properties": {
          "finding_id":     { "type": "string", "pattern": "^SEC-V-\\d{3}$" },
          "severity": {
            "type": "string",
            "enum": ["Critical", "High", "Medium", "Low", "Informational"]
          },
          "category":       { "type": "string", "minLength": 1 },
          "description":    { "type": "string", "minLength": 1 },
          "location":       { "type": "string", "minLength": 1 },
          "recommendation": { "type": "string", "minLength": 1 },
          "scanner_covered":{ "type": "boolean" }
        }
      }
    },
    "human_summary": { "type": "string", "minLength": 1 }
  }
}
```

**Prohibited fields (hard fail if present):**
- `verdict`, `pass`, `block`, `pass_block`, or any field whose name or value
  contains a pass/block determination. The orchestrator derives this; the agent
  must not emit it.

### A.2 Machine-checkable output contract: security-governance

Every governance agent output must validate against this schema.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SecurityGovernanceOutput",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "request_title", "build_type", "applied_sensitivity",
    "findings", "human_summary"
  ],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "build_type": {
      "type": "string",
      "enum": ["code", "agent_creation", "config_applied",
               "config_instructions"]
    },
    "applied_sensitivity": {
      "type": "string",
      "enum": ["none", "internal", "customer", "financial", "regulated"]
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "finding_id", "severity", "category", "description",
          "location", "governance_reference", "recommendation",
          "scanner_covered"
        ],
        "properties": {
          "finding_id":           { "type": "string", "pattern": "^SEC-G-\\d{3}$" },
          "severity": {
            "type": "string",
            "enum": ["Critical", "High", "Medium", "Low", "Informational"]
          },
          "category":             { "type": "string", "minLength": 1 },
          "description":          { "type": "string", "minLength": 1 },
          "location":             { "type": "string", "minLength": 1 },
          "governance_reference": { "type": "string", "minLength": 1 },
          "recommendation":       { "type": "string", "minLength": 1 },
          "scanner_covered":      { "type": "boolean" }
        }
      }
    },
    "human_summary": { "type": "string", "minLength": 1 }
  }
}
```

**Prohibited fields (hard fail if present):**
- Same as vulnerabilities agent: no verdict, pass, block, or pass_block field.

### A.3 Per-schema assertions (both agents)

Every fixture for either agent asserts:

- `schema_valid: true`
- `finding_ids_sequential: true` -- IDs are sequential from 001 with no gaps
- `finding_ids_correct_prefix: true` -- vulnerability findings use SEC-V-NNN;
  governance findings use SEC-G-NNN; no cross-agent prefix pollution
- `no_verdict_field: true` -- output contains no verdict/pass/block field
- `human_summary_non_empty: true`
- `no_prose_outside_json: true`

Governance agent only:
- `applied_sensitivity_correct: true` -- applied_sensitivity matches the
  expected mapping given the input data_sensitivity (including the
  unspecified -> customer rule)
- `governance_reference_non_empty: true` -- every finding has a non-empty
  governance_reference

---

## PART B -- Vulnerability agent substantive cases (SEC-V series)

### B.1 Scoring rubric (1--5)

Hybrid: schema and field rules are machine-checked in Part A. The rubric
covers judgment quality. Implemented as a judge-model call, three runs per
case, median scored.

| Dimension | What to look for |
|---|---|
| **Finding specificity** | Each finding identifies a specific location (file:line or named section) and explains the risk in the context of THIS build -- not a generic description of the vulnerability class. |
| **Scanner division respected** | Scanner-covered findings (scanner_covered: true) add contextual value the scanner output does not -- exploitability analysis, severity adjustment, or fix-viability note. Findings that only restate the scanner report score low. |
| **Severity calibration** | Severity matches the defined rubric: Critical requires no precondition beyond reaching the code path; High requires a specific precondition; Medium is indirect or chained; Low is a weakness without an immediate exploitable path. |
| **Recommendation actionability** | Each recommendation is specific and scoped: it names what to change, where, and (where relevant) what to do about current exposure. Generic "fix the issue" recommendations score low. |
| **Scope discipline** | No governance findings in the findings array. Governance observations are noted in human_summary only. |
| **human_summary R&D readiness** | A security practitioner who has not seen the intake transcript can begin an R&D review from the summary alone. Summary includes: overall verdict, findings overview by severity, two to three most significant contextual observations, and any condition requiring R&D attention. |
| **Prompt/agent build coverage** | When build_type is agent_creation or config_instructions, the review explicitly addresses prompt-injection surface, capability grants, and tool-call safety -- not just code-style issues. |

Score interpretation:
- **5** -- Exemplary; would not be improved by an expert rewrite.
- **4** -- Solid; minor polish only.
- **3** -- Acceptable; one or two dimensions are weak but the output is usable.
- **2** -- Material issues; output should be re-run or escalated.
- **1** -- Output is wrong or unsafe; merge blocked.

### B.2 Vulnerability test cases (SEC-V1 -- SEC-V6)

Each case is one fixture file (YAML) with: `intake_extract`, `transcript`,
`stack_check_finding`, `qa_findings` (may be absent), `scanner_findings`,
`mock_repo_contents`, and `expected` assertions.

**SEC-V1 -- Critical contextual finding, code build, not scanner-caught**

- Build type: code. data_sensitivity: customer.
- Scanner findings: clean across all types.
- Mock repo: contains an API key derived programmatically from a non-secret
  environment variable (reversible, predictable).
- Expected: at least one Critical finding with category Secrets;
  scanner_covered: false; location identifies the specific file and line;
  description explains why the scanner missed it (no static literal);
  recommendation includes key rotation; human_summary mentions the Critical
  finding prominently.

**SEC-V2 -- High finding, scanner-overlap with required contextual value**

- Build type: code. data_sensitivity: internal.
- Scanner findings: SCA flags a known CVE (High) on a dependency.
- Mock repo: the flagged dependency is called on user-supplied input with
  no input validation; the CVE is an injection-class issue.
- Expected: the finding appears with scanner_covered: true; the description
  adds exploitability context the scanner output does not (direct user-input
  path, no validation); recommendation includes both upgrade and call-site
  hardening; the finding is not a restatement of the scanner output.

**SEC-V3 -- Injection finding, agent/prompt build**

- Build type: agent_creation. data_sensitivity: customer.
- Scanner findings: empty (no SAST for prompt builds).
- Mock repo: agent system prompt grants a file_write tool; user-visible
  prompt includes a section instructing the agent to summarize "any document
  the user references by path."
- Expected: at least one finding with category Prompt-injection; description
  explains how the combination of file_write and user-controlled path input
  creates a write-anywhere injection surface; location identifies the prompt
  file and the relevant section; recommendation proposes path restriction and
  tool scope reduction; no governance findings in the findings array.

**SEC-V4 -- Auth/authz gap, code build**

- Build type: code. data_sensitivity: financial.
- Scanner findings: clean.
- Mock repo: an API endpoint accepts a user_id parameter and returns that
  user's financial records without verifying the requesting session owns
  the specified user_id (IDOR pattern).
- Expected: at least one finding with category Authorization; severity
  Critical or High; description names the IDOR pattern and explains the
  missing ownership check; location is the specific endpoint handler;
  recommendation proposes adding an ownership assertion before the data
  retrieval.

**SEC-V5 -- Clean pass, code build, Low-sensitivity**

- Build type: code. data_sensitivity: internal.
- Scanner findings: one Informational SCA notice (no fix needed, noted by
  scanner).
- Mock repo: straightforward internal read-only utility with no auth surface
  and no external calls.
- Expected: findings array is empty OR contains only Informational entries;
  the scanner Informational notice may appear with scanner_covered: true if
  the agent has contextual commentary, or may be omitted if it adds nothing;
  human_summary confirms scope of review and clean result; no Critical or
  High findings.

**SEC-V6 -- Clean pass, prompt build, config_instructions**

- Build type: config_instructions. data_sensitivity: internal.
- Scanner findings: not run (config_instructions build; scanner block absent).
- Mock repo: a short set of instructions for internal team communication
  formatting; no tool calls, no data access, no AI engine.
- Expected: findings array is empty; human_summary notes that scanner did
  not run (config_instructions build type), states the scope of the manual
  review (instructions reviewed for logic that would cause unsafe or over-
  privileged actions), and confirms no findings; human_summary does NOT
  claim scanner coverage that did not occur.

---

## PART C -- Governance agent substantive cases (SEC-G series)

### C.1 Scoring rubric (1--5)

| Dimension | What to look for |
|---|---|
| **Sensitivity tier applied correctly** | applied_sensitivity matches the expected value, including the unspecified -> customer mapping. The tier is stated explicitly in the output and in the human_summary. |
| **Governance standard grounding** | Every finding cites a specific section or rule from the governance standard. Findings without a governance reference score low regardless of their factual content. |
| **Data flow coverage** | The review identifies where data enters, is stored, is transmitted, and (for agent builds) what data appears in the context window, what tool calls return, and what persists in logs. Reviews that only check access grants without tracing data flows score lower. |
| **Prompt/agent build treatment** | For agent_creation and prompt builds, the review explicitly addresses agent-data-access scope, tool definitions, and whether user input could cause unintended data access. Generic "this is a code review" framing applied to a prompt build scores low. |
| **Finding specificity** | Each finding identifies a specific location and maps the risk to the build in context. Generic governance statements without a specific location score low. |
| **Recommendation actionability** | Recommendations are specific: they name the change, the correct governance-compliant alternative, and (where relevant) what to do about current exposure. |
| **Scope discipline** | No vulnerability findings (injection, secrets-in-code, auth/authz gaps) in the findings array. Vulnerability observations are in human_summary only. |
| **human_summary R&D readiness** | Meets the same bar as the vulnerability agent: self-contained, written for a practitioner who has not seen the intake transcript, explicitly states the applied sensitivity tier and the most significant data-flow observations. |

Score interpretation matches Part B.1.

### C.2 Governance test cases (SEC-G1 -- SEC-G6)

Each case is one fixture file with: `intake_extract`, `transcript`,
`stack_check_finding`, `qa_findings` (may be absent), `scanner_findings`,
`mock_repo_contents`, `mock_governance_standard`, `mock_registry_responses`,
and `expected` assertions.

**SEC-G1 -- Critical finding, agent build, access-scope overage**

- Build type: agent_creation. data_sensitivity: customer.
  applied_sensitivity expected: customer.
- Mock repo: agent tool definition grants read access to the full customer
  record table; the agent's task requires only three specific fields from
  the support ticket.
- Mock governance standard: §4.2 requires least-privilege scoping for
  customer-data agents.
- Expected: at least one Critical finding with category Agent-data-access;
  governance_reference cites §4.2; description names the specific over-grant
  and explains the exploitation path (user prompt manipulation); recommendation
  proposes scoping the tool to the minimum required fields, enforced server-
  side; applied_sensitivity is "customer"; no vulnerability findings in array.

**SEC-G2 -- High finding, regulated data logged in plaintext**

- Build type: code. data_sensitivity: regulated.
  applied_sensitivity expected: regulated.
- Mock repo: a processing function logs regulated fields (SSN, financial
  amount) at INFO level to the general application logger.
- Mock governance standard: §6.1 prohibits regulated fields in general-
  purpose log sinks without audit controls.
- Expected: at least one High finding with category Logging-retention;
  governance_reference cites §6.1; description identifies the specific log
  call and the logging sink; recommendation distinguishes between removing
  the log call and routing to the audit sink.

**SEC-G3 -- Medium finding, data transmitted to a tool below its
  sensitivity clearance**

- Build type: code. data_sensitivity: financial.
  applied_sensitivity expected: financial.
- Mock repo: build sends a financial summary payload to a notification tool.
- Mock registry: the notification tool's sensitivity clearance is "internal"
  (below "financial").
- Mock governance standard: §5.1 requires all integration targets to be
  cleared at or above the data tier being transmitted.
- Expected: at least one Medium or High finding with category Access-scope
  (or similar); governance_reference cites §5.1; registry_query was used
  (confirmed by mock_registry_responses having the notification tool lookup);
  description explains the clearance gap; recommendation proposes either
  upgrading the tool's clearance through the registry process or scrubbing
  financial fields before the notification call.

**SEC-G4 -- data_sensitivity: unspecified, sensitivity-until-confirmed rule
  applied**

- Build type: code. data_sensitivity: unspecified.
  applied_sensitivity expected: customer (unspecified -> customer mapping).
- Mock repo: a build that would be clean under "internal" rules but has a
  data-handling pattern that violates customer-tier governance (e.g., stores
  a user-provided field in a non-cleared persistence layer).
- Expected: applied_sensitivity is "customer" in the output; the finding
  references the customer-tier rule that triggered it; human_summary states
  that unspecified sensitivity was treated as customer per the sensitivity-
  until-confirmed rule; the finding would not appear if the tier were "internal".
  This case explicitly tests that the mapping is applied and reflected in output.

**SEC-G5 -- Clean pass, config build, internal sensitivity**

- Build type: config_applied. data_sensitivity: internal.
  applied_sensitivity expected: internal.
- Mock repo: a config enabling a weekly digest email from a project board;
  reads project metadata only; no customer or regulated fields in scope;
  integration target is an internal email relay cleared for internal tier.
- Expected: findings array is empty; applied_sensitivity is "internal";
  human_summary states the sensitivity tier applied, confirms the data flows
  reviewed (project metadata, email relay), confirms the integration target's
  clearance was checked, and states no findings.

**SEC-G6 -- Prompt build, clean governance pass but explicit data-scope
  statement required**

- Build type: agent_creation. data_sensitivity: internal.
  applied_sensitivity expected: internal.
- Mock repo: an agent that summarizes internal project status updates;
  tool definitions are correctly scoped to read-only project fields;
  no customer or regulated data in scope; no over-grant.
- Expected: findings array is empty; human_summary explicitly states (a)
  what data the agent is designed to access, (b) what data it could reach
  (the same, per correct scoping), and (c) that the scopes are aligned with
  governance standard requirements for the internal tier. This case tests
  that the agent does not silently skip the data-scope statement for a
  clean prompt build.

---

## PART D -- Disagreement-detection cases (SEC-D series)

These cases test the orchestrator's ability to detect a pass/block split
between the two agents' outputs. The agents produce findings arrays; the
orchestrator computes effective verdicts and compares them. The eval harness
verifies that the agents' outputs are shaped to support deterministic
disagreement detection.

Effective verdict derivation rule (orchestrator logic, not agent logic):
  effective_verdict = "block" if any finding has severity Critical or High
  effective_verdict = "pass"  otherwise

Disagreement definition: one agent's effective_verdict is "pass" and the
other's is "block".

### D.1 -- One agent blocks, other passes (disagreement; routes to Director)

- Mock vulnerability output: one Critical finding (SEC-V-001).
- Mock governance output: empty findings array.
- Effective verdicts: vulnerability = block; governance = pass.
- Expected assertions:
  - `vulnerability_effective_verdict: "block"` (derived from Critical finding)
  - `governance_effective_verdict: "pass"` (derived from empty findings)
  - `disagreement_detected: true`
  - `orchestrator_action: "route_to_director"`
  This case tests that the agents' outputs are structured to support the
  effective-verdict derivation and that a split is detectable deterministically.

### D.2 -- Both agents block on different findings (additive, no disagreement)

- Mock vulnerability output: one High finding (SEC-V-001).
- Mock governance output: one Critical finding (SEC-G-001).
- Effective verdicts: vulnerability = block; governance = block.
- Expected assertions:
  - `vulnerability_effective_verdict: "block"`
  - `governance_effective_verdict: "block"`
  - `disagreement_detected: false`
  - `orchestrator_action: "block_build"` (both block; Director notified for
    awareness, not for adjudication)
  This case tests that two blocks on different findings are treated as
  additive, not as a disagreement.

### D.3 -- Both agents pass (clean; no disagreement)

- Mock vulnerability output: empty findings array.
- Mock governance output: empty findings array.
- Effective verdicts: vulnerability = pass; governance = pass.
- Expected assertions:
  - `vulnerability_effective_verdict: "pass"`
  - `governance_effective_verdict: "pass"`
  - `disagreement_detected: false`
  - `orchestrator_action: "advance_to_director_gate"`

---

## PART E -- Hard-fail pattern detection

The following patterns trigger an automatic merge block regardless of rubric
scores. These are deterministic checks, not judge-model calls.

### E.1 Scope violations

**Governance finding in vulnerability output:**
  Pattern: any finding in the vulnerability agent's output where the category
  is Data-handling, Access-scope, Isolation, Regulated-data, Prompt-data-scope,
  Agent-data-access, or Logging-retention.
  Trigger: merge blocked. Governance findings in the wrong output indicate a
  prompt scoping failure that must be corrected before production use.

**Vulnerability finding in governance output:**
  Pattern: any finding in the governance agent's output where the category
  is Injection, Secrets, Authentication, Authorization, Unsafe-call,
  Dependency, or Prompt-injection.
  Trigger: merge blocked. Same reasoning.

### E.2 Verdict field present

  Pattern: output JSON contains any key named verdict, pass, block,
  pass_block, or any similar field whose value is a pass/block determination.
  Trigger: merge blocked on either agent's output.

### E.3 Severity outside vocabulary

  Pattern: any finding where severity is not one of Critical, High, Medium,
  Low, Informational (exact strings, case-sensitive).
  Trigger: merge blocked.

### E.4 Finding ID format violation

  Pattern: vulnerability findings with IDs not matching SEC-V-NNN, or
  governance findings with IDs not matching SEC-G-NNN.
  Trigger: merge blocked.

### E.5 Governance finding missing governance_reference

  Pattern: governance agent finding where governance_reference is empty or
  absent.
  Trigger: merge blocked. A governance finding without a standard reference
  is an opinion, not a finding.

### E.6 Sensitivity tier mapping error

  Pattern: governance agent output where applied_sensitivity is "unspecified"
  (the input value, not a valid output value), or where applied_sensitivity
  is "none" or "internal" when data_sensitivity input was "unspecified".
  Trigger: merge blocked. The sensitivity-until-confirmed rule is non-
  negotiable.

---

## PART F -- CI rules

Inherited from orchestrator-contract v1.1.0 §7.3 with security-specific gates:

- **Any schema validation failure (either agent)** -- merge blocked.
- **Any hard-fail pattern detected (Part E)** -- merge blocked.
- **Any disagreement-detection case fails (SEC-D series)** -- merge blocked.
  The disagreement mechanic is safety-critical; regressions here block
  unconditionally.
- **Rubric median drops below 3 on any dimension for either agent, or drops
  more than 1 point below the previous baseline on any dimension** -- merge
  blocked.
- **Rubric improves** -- new baseline recorded.

Security agent evals run on a schedule and on every PR touching either
security agent prompt. Schema validation and hard-fail detection run on every
commit.

The harness records the prompt version + commit hash on every run so
regressions are traceable to the change that introduced them.

---

## G. Metadata footer

- **Artifact:** `security-evals`
- **Version:** `1.0.0` · **Owner:** Director · **Status:** Draft
- **Type:** Eval scaffold (not a prompt)
- **Covers:** `security-vulnerabilities` v1.0.0, `security-governance` v1.0.0
- **Changelog:** `v1.0.0` initial scaffold covering both security agents plus Finalization pass (2026-06-29): baseline citations aligned to Architecture v0.3 / orchestrator-contract v1.1.0; build-avenue/engine vocabulary normalized (underscored avenue, lowercase engine, non-canonical instructions-only value dropped) to match the agent contracts.
  combined disagreement-detection cases.
