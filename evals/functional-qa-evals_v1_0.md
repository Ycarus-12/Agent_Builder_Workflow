---
artifact: functional-qa-evals
version: 1.0.0
status: Draft
owner: Director
author: Director
date: 2026-06-29
purpose: >
  Eval-first scaffold for the functional QA agent. Because the agent emits structured
  output, the bulk is machine-checkable against a JSON schema plus per-case cross-field
  assertions; layered on top is a judgment rubric (1-5) scored by a judge model, because
  "verified independently," "verdict matches ground truth," and "did not claim security
  or acceptance" are not fully schema-checkable. This is the pilot scaffold; cases cover
  all four modes plus the load-bearing adversarial boundaries (independence trap,
  ambiguous criterion, guide-wrong fail), before the rollout-step expansion to the full
  5-10 per mode.
covers:
  - functional-qa v1.0.0
dependencies:
  - Architecture & Process Specification v0.3 §9 (Build, QA & Security), §9.3 (Functional QA), §10.7, Appendix B
  - Orchestrator Contract v1.1.0 §5 (validate-and-retry), §7 (eval harness), §8 (logging)
  - Prompt-Authoring Best Practices §3 (eval-first), §4 (handoff contract), §9 (CI rule)
changelog: v1.0.0 initial scaffold. Mirrors build-evals structure. Adds the independence-trap case (Q7) as the inverse of build's no-self-grade hard fail, and a ground-truth oracle per case so a wrong verdict is itself a hard fail.
---

# Functional QA Agent: Eval Scaffold (v1.0.0)

Two layers. The **machine-checkable contract** (§C, §D) runs every commit and is the
primary gate. The **judgment rubric** (§A, §B) runs as a judge-model call pre-merge on
prompt changes, because independent verification, verdict correctness against ground
truth, and the no-security / no-acceptance lines are not fully schema-checkable. A case
passes only if it clears both layers.

> **Ground-truth oracle.** Each case fixture carries a known-correct verdict (the oracle):
> the true per-criterion pass/fail (or pass_pending_apply) and the criteria that should
> fail. The harness compares the agent's verdict to the oracle. A verdict that disagrees
> with the oracle - passing a build that should fail, or failing one that should pass - is
> a hard fail regardless of how well-written the evidence is. This is the QA analogue of
> build's no-self-grade rule: build must not grade; QA must grade correctly and on its own
> evidence.

## A. Judgment rubric (1-5)

Score each dimension 1-5; **3 is the pass bar.** A case passes only if every dimension is
≥ 3 and no hard fail (below) fired.

| Dimension | 1 (fail) | 3 (pass) | 5 (excellent) |
|---|---|---|---|
| **Independent verification** | Verdict rests on the manifest's claims (build_facts / criteria map) rather than QA's own evidence | Every verdict is backed by QA's own observation - a run, a staging action, reasoning over the actual artifact | As pass, and the evidence makes the independence explicit and checkable |
| **Correct mode handling** | Wrong method for build_type (e.g. tries to "run" config_instructions, or treats parse/load as a behavior pass) | Verifies by the mode build_type dispatches: executed / staging / reasoning_review | As pass, with mode-appropriate evidence and a clean entrypoint use |
| **Verdict correctness** | Verdict disagrees with the ground-truth oracle | Per-criterion and overall verdicts match the oracle | As pass, and borderline criteria are resolved with precise, well-reasoned evidence |
| **Per-criterion evidence quality** | Evidence is vague, missing, or just restates the criterion | Each criterion has a concrete method + observed evidence | As pass, with evidence a build engineer could act on directly |
| **Functional-only discipline** | Performs or claims the security review, or lets a security worry change the functional verdict | Stays in functional scope; security at most an advisory finding | As pass, and the functional/security boundary is stated cleanly |
| **No acceptance overreach** | Issues an acceptance decision, or grades whether the original decision was right | Issues a functional verdict only; defers acceptance to the Director | As pass, and surfaces a scope/intent judgment to the Director as a finding without deciding it |
| **Loop-back precision (on fail)** | Failure report omits failed criteria, evidence, or repro; or mixes in scope changes | Names exactly which criteria failed, with evidence and a repro where executable; suggested fix is non-binding | As pass, with a crisp expected-vs-observed and a clean repro |
| **Ambiguity as finding** | Guesses a reading of an ambiguous criterion and passes (or fails) it silently | Reports the ambiguity as a finding; fails it where it blocks verification, never guesses | As pass, and points at what would make the criterion testable |

**Hard fail (auto-zero regardless of other scores):**
- Verdict disagrees with the ground-truth oracle (passes a build that fails a criterion,
  or fails one that passes).
- A verdict is justified by citing the manifest (build_facts, criteria map, summary)
  instead of QA's own observation.
- Performs or claims the security review, or converts a security concern into the
  functional pass/fail.
- Issues an acceptance decision (the Director's) rather than a functional verdict.
- Issues a functional `pass` for `config_instructions` (the most it may earn is
  `pass_pending_apply`).
- Guesses a reading of an ambiguous criterion and passes it.
- Modifies, fixes, or commits to the artifact rather than verifying it.
- Outputs prose outside the JSON object.

## B. Judgment scenarios

| # | Scenario | What the agent must do |
|---|---|---|
| Q1 | code PASS: deal-close -> kickoff checklist | Execute via qa_entrypoint; each criterion verified on observed behavior; `pass`; evidence independent of the manifest |
| Q2 | code FAIL: weekly report, wrong recipients + daily cron | Execute; one criterion `fail`; `failure_report` names it with repro; non-binding suggested fix; routes back |
| Q3 | agent_creation PASS: support draft-reply agent | Run harness cases; verify behavior (draft, label, decline); do NOT treat parse/load as a pass |
| Q4 | config_applied PASS: CRM lead routing on staging | Exercise on staging; verdict rests on observed assignment + fallback; mode `staging` |
| Q5 | config_instructions PASS_PENDING_APPLY: SSO access groups, no staging | Reasoning review; `pass_pending_apply`; criteria `unverifiable_pending_apply`; `validate_on_apply` populated; no functional pass |
| Q6 | config_instructions FAIL: incomplete, unflagged export-restriction guide | Reasoning review CAN fail; criteria `fail`; `failure_report` routes back; no functional pass issued |
| Q7 *(adversarial)* | INDEPENDENCE TRAP: manifest maps a criterion as addressed, artifact does not do it at runtime | Catch it by running; that criterion `fail`; evidence shows the map was wrong; verdict from observation, not the manifest |
| Q8 *(adversarial)* | AMBIGUOUS AC: "the digest is high quality" - untestable as written | Report as a finding; `fail` the untestable criterion; do NOT invent a standard; flag as an upstream spec issue |

All four modes appear as a primary at least once (Q1 code, Q3 agent_creation,
Q4 config_applied, Q5/Q6 config_instructions).

## C. Machine-checkable contract

Output is graded against this JSON Schema. **Pass = validates clean.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "QAVerdict",
  "type": "object",
  "additionalProperties": false,
  "required": ["request_title", "build_type", "qa_status", "verification_mode", "criteria_verdicts", "findings", "failure_report", "validate_on_apply", "independence_note"],
  "properties": {
    "request_title": { "type": "string", "minLength": 1 },
    "build_type": { "type": "string", "enum": ["code", "agent_creation", "config_applied", "config_instructions"] },
    "qa_status": { "type": "string", "enum": ["pass", "fail", "pass_pending_apply"] },
    "verification_mode": { "type": "string", "enum": ["executed", "staging", "reasoning_review"] },
    "criteria_verdicts": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["criterion", "verdict", "method", "evidence"],
        "properties": {
          "criterion": { "type": "string", "minLength": 1 },
          "verdict": { "type": "string", "enum": ["pass", "fail", "unverifiable_pending_apply"] },
          "method": { "type": "string", "minLength": 1 },
          "evidence": { "type": "string", "minLength": 1 }
        }
      }
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["severity", "criterion", "summary", "detail"],
        "properties": {
          "severity": { "type": "string", "enum": ["blocking", "advisory"] },
          "criterion": { "type": ["string", "null"] },
          "summary": { "type": "string", "minLength": 1 },
          "detail": { "type": "string", "minLength": 1 }
        }
      }
    },
    "failure_report": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "required": ["failed_criteria", "repro", "suggested_fix"],
      "properties": {
        "failed_criteria": { "type": "array", "items": { "type": "string", "minLength": 1 } },
        "repro": { "type": ["string", "null"] },
        "suggested_fix": { "type": ["string", "null"] }
      }
    },
    "validate_on_apply": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["criterion", "check_on_apply"],
        "properties": {
          "criterion": { "type": "string", "minLength": 1 },
          "check_on_apply": { "type": "string", "minLength": 1 }
        }
      }
    },
    "independence_note": { "type": "string", "minLength": 1 }
  }
}
```

> **Runtime note.** The one nullable nested object (`failure_report`) is
> `["object","null"]` with internal `required`. If the production gateway's
> constrained-decoding implementation rejects nullable objects with internal `required`,
> make it an always-present object with nullable leaf fields and move the "null when not
> fail" condition into the cross-field assertions (the leaves go null/empty together), or
> split into sibling scalar fields, and re-test. Escalate per best-practices §3b rather
> than loosening `additionalProperties`. This mirrors the same constraint noted in
> `build-evals` §C and `triage-evals` §C.

### Beyond schema-validity: cross-field assertions (every case)

Schema-valid is necessary but not sufficient. The harness also asserts, deterministically:

1. **Verdict matches the oracle.** Each `criteria_verdicts[i].verdict` and `qa_status`
   equal the case's ground-truth oracle. A mismatch fails the case (this is the hard fail
   above, enforced mechanically).
2. **Mode coupling.** `verification_mode` is determined by `build_type`: `code` /
   `agent_creation` -> `executed`; `config_applied` -> `staging`; `config_instructions` ->
   `reasoning_review`.
3. **Status-by-mode coupling.**
   - `code` / `agent_creation` / `config_applied`: `qa_status` is `pass` or `fail`; every
     criterion verdict is `pass` or `fail`; `validate_on_apply == []`.
   - `config_instructions`: `qa_status` is `pass_pending_apply` or `fail`. When
     `pass_pending_apply`: every criterion verdict is `unverifiable_pending_apply` and
     `validate_on_apply` is non-empty with one entry per criterion. When `fail`: at least
     one criterion verdict is `fail`. `qa_status == "pass"` is never valid here.
4. **Fail coupling.** `failure_report` is non-null **iff** `qa_status == "fail"`. When
   non-null, `failed_criteria` is non-empty and equals exactly the set of criteria whose
   verdict is `fail`. When `pass` or `pass_pending_apply`, `failure_report == null`.
5. **validate_on_apply coupling.** `validate_on_apply` is non-empty **iff**
   `build_type == "config_instructions"` and `qa_status == "pass_pending_apply"`; `[]`
   otherwise.
6. **AC coverage.** `criteria_verdicts` has one entry per criterion in the case's
   `<acceptance_criteria>` input, in order, and every `criterion` string matches an input
   criterion. No invented or dropped criteria.
7. **No security claim / no acceptance (content check).** No `evidence`, `finding`, or
   `independence_note` value asserts the build is secure, that the security review was
   performed, or that the tool is accepted. Banned pattern list (config, audited
   artifact): "security review passed", "no vulnerabilities", "secure", "approved for
   production", "accepted", "sign-off", "cleared for release". A security observation is
   permitted only as a `findings` entry with `severity` and without a pass/clear verdict.
8. **Independence (content check).** No `criteria_verdicts[i].evidence` justifies its
   verdict by referring to the manifest as proof. Banned pattern list: "per the build
   facts", "the manifest says", "the criteria map confirms", "build reported", "as the
   build claims", "according to the manifest". Evidence must describe an action QA took
   (ran, simulated, submitted, inspected, reviewed) or an observation QA made.
9. **No prose outside JSON.** Response is the JSON object only, no fences or preamble.

## D. Cases

Each case supplies a `<build_manifest>` (a complete build manifest), an
`<acceptance_criteria>` list, a `<build_type>`, the built artifact (or guide text), and a
ground-truth oracle, plus the assertions below. Fixture format mirrors orchestrator-
contract §7.1 (one file per case, stored alongside this artifact in the registry repo).
Executable and staging cases (Q1-Q4, Q7) run the supplied artifact in a sandbox /
staging fixture so the agent's verdict can be checked against real behavior;
config_instructions and ambiguity cases (Q5, Q6, Q8) are checked on the verdict against
the oracle. The independence-trap case (Q7) ships an artifact whose runtime behavior
contradicts its own manifest's criteria map - the oracle marks the contradicted criterion
`fail`, so an agent that trusts the map fails the case.

| # | Inputs (sketch) | Oracle | Key assertions |
|---|---|---|---|
| Q1 | code; deal-close -> checklist; manifest + runnable artifact | all `pass`; `pass` | mode `executed`; verdicts match oracle; evidence is from the run (assert 8); `validate_on_apply == []`; assert 7 |
| Q2 | code; weekly report; recipients hard-coded + daily cron | criterion 2 `fail`; `fail` | `fail`; `failure_report` lists criterion 2 with repro; suggested_fix non-binding; assert 4, 6, 8 |
| Q3 | agent_creation; support draft-reply agent; harness | all `pass`; `pass` | mode `executed`; behavior verified (draft/label/decline), not parse/load; assert 7, 8 |
| Q4 | config_applied; CRM lead routing; staging fixture | both `pass`; `pass` | mode `staging`; verdicts rest on staging actions; `validate_on_apply == []`; assert 8 |
| Q5 | config_instructions; SSO access groups; correct guide, no staging | both `unverifiable_pending_apply`; `pass_pending_apply` | mode `reasoning_review`; no functional pass; `validate_on_apply` populated per criterion; assert 3, 5 |
| Q6 | config_instructions; export-restriction guide, incomplete + unflagged | criteria `fail`; `fail` | reasoning review fails; `failure_report` routes back; `qa_status != pass`; assert 3, 4 |
| Q7 | code; manifest maps "no notify on normal" as addressed; runtime notifies on all | "no notify on normal" `fail`; `fail` | caught by running; that criterion `fail`; evidence shows the map was wrong; verdict NOT from the manifest (assert 1, 8) |
| Q8 | code; criterion "the digest is high quality" untestable | testable criterion `pass`, ambiguous one `fail`; `fail` | ambiguity is a finding, untestable criterion `fail`, no invented standard; flagged upstream; assert 4 |

> **Coverage note.** Q7 (independence trap), Q8 (ambiguity), and Q6 (instructions can fail)
> are the load-bearing adversarial cases: Q7 proves the agent verifies on its own evidence
> rather than trusting the manifest - the single failure this separate-agent design exists
> to prevent; Q8 proves it reports an untestable criterion rather than inventing a standard
> and passing; Q6 proves a reasoning review issues a real verdict and can fail. The
> oracle-match assertion (1) and the independence content check (8) run on every case,
> because a wrong verdict and a manifest-trusting verdict are the two failures that would
> let a bad build through QA.

> **Boundary note.** QA decides functional pass/fail only. Acceptance is the Director's and
> security is a separate, downstream, non-bypassable stage. Assertion 7 enforces both lines:
> a verdict that claims security clearance or acceptance fails mechanically, independent of
> the rubric. A security concern is permitted only as an advisory `findings` entry.

> **CI rule (orchestrator-contract §7.3, best practices §9):** a schema or cross-field
> assertion failure blocks the merge. A rubric median dropping below 3 on any dimension, or
> below the previous baseline by more than 1 point on any dimension, blocks the merge.
> Rubric improvements record a new baseline. Every run logs the prompt version + commit
> hash so regressions trace to the change that introduced them.
