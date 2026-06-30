# ADR 0001 — Scanner tooling selection

- **Status:** Proposed (pending R&D co-sign — see §6)
- **Date:** 2026-06-30
- **Owner:** Director · **Co-owner:** R&D (owns CI plumbing and build environments)
- **Decision authority:** Director, co-signed by R&D
- **Resolves:** context_06_29.md §7 open decision #4 ("The specific scanner tool
  selection and CI plumbing"); the "scanner tooling selection" item on the
  CLAUDE.md deferred list.

## 1. Context

The two security agents (`security-vulnerabilities`, `security-governance`) run a
*contextual* review **after** deterministic scanners run in CI on the build's
pull request (Architecture §9.4). The scanners catch the mechanical issues; the
agents focus on what scanners miss. This ADR picks the concrete scanner tools.

What is already **frozen** and therefore constrains the choice:

- **The normalized output contract.** Both agents consume a `<scanner_findings>`
  block in this exact shape (`agents/security-vulnerabilities_v1_0.md`, and the
  `security_vulnerabilities.json` / `security_governance.json` schemas):

  ```json
  {
    "sast":    [{ "rule_id", "severity", "file", "line", "message" }],
    "sca":     [{ "package", "version", "cve", "severity", "fix_version" }],
    "secrets": [{ "type", "file", "line", "detector" }]
  }
  ```

  An **absent array** = that scanner ran and found nothing. An **absent block** =
  that scanner type did not run for this build.

- **The severity vocabulary.** Findings must map to
  `Critical | High | Medium | Low | Informational` — the same five values the
  orchestrator's reconciler thresholds on (`orchestrator/app/security_review.py`,
  `_SEVERITY_RANK`). Critical blocks and is non-bypassable.

- **The orchestrator seam.** `scanner_findings` is already a context block plumbed
  to both security agents (`orchestrator/app/agents.py`, `_SECURITY_BLOCKS`). It
  needs a *producer*; no orchestrator change is required to adopt scanners.

- **The platform.** GitHub + GitHub Actions CI; primary language Python, but build
  artifacts may be polyglot (the agent examples reference both `.py` and `.js`).

## 2. Decision

**Constraint for this version: free / OSS tools only.** No paid tiers, no GitHub
Advanced Security. Paid upgrades (e.g. Semgrep Pro engine, a managed SCA feed) are
deferred to a later revision and gated on demonstrated need. Every tool below is
free to run in CI; note the Semgrep free-tier caveat in §6.

Adopt an **open-source, GitHub-Actions-native** scanner set, normalized into the
frozen contract by an adapter we own:

| Contract slot | Tool | Rationale |
|---|---|---|
| **SAST** (`sast`) | **Semgrep OSS** (community rulesets) | Multi-language (Python + JS + more), large free ruleset, SARIF output, trivial in Actions. Custom rules also back the prompt-injection check (§4). **Bandit** is a per-repo opt-in, not a default (§6). |
| **SCA** (`sca`) | **Trivy** | One tool covers dependency CVEs (+ IaC misconfig); emits exactly `package / version / cve / severity / fix_version`. Free, no GitHub Advanced Security dependency. OSV-Scanner rejected: SCA-only, no misconfig coverage (§6). |
| **Secrets** (`secrets`) | **Gitleaks** | Fast, OSS, JSON maps cleanly to `type / file / line / detector`; pair with GitHub push-protection where available. |
| **Glue** | **Normalizer adapter** (our code, in the build-artifact repo CI) | Maps each tool's SARIF/JSON into the `scanner_findings` contract and applies the severity mapping (§3). Keeps the contract stable across tool swaps — the same provider-neutral seam discipline used for the model gateway. |

All picks are free, OSS, vendor-neutral, and run natively in GitHub Actions.

## 3. Severity normalization

Each tool has its own severity scale; the adapter maps them deterministically into
the canonical five values before the agents and reconciler see them. The mapping
itself is part of this decision (record any deviation as a follow-up ADR):

| Tool scale | → Canonical |
|---|---|
| Semgrep `ERROR` | High (or Critical if the rule is tagged for it) |
| Semgrep `WARNING` | Medium |
| Semgrep `INFO` | Informational |
| Trivy / CVE `CRITICAL` | Critical |
| Trivy / CVE `HIGH` | High |
| Trivy / CVE `MEDIUM` / `LOW` | Medium / Low |
| Gitleaks (any match) | High (a confirmed live secret is escalated to Critical) |

CVSS-derived severities follow the tool's own banding; a secret confirmed live
(e.g. Gitleaks/TruffleHog verification) is escalated to Critical.

## 4. Coverage by build type (Architecture §9.4)

The scanner set runs conditionally on `build_type`:

- **`code`** — full set: SAST + SCA + secrets.
- **`config_applied` / `config_instructions`** — secret-scanning on any
  config-as-code; the data-governance agent does the rest. No SAST/SCA.
- **`agent_creation`** — a **prompt-injection / safety check in place of SAST**
  (Semgrep custom ruleset over prompt and tool-definition files: over-broad tool
  scopes, capability over-grant, unsafe tool wiring), plus secret-scanning;
  data-governance still applies.
- **Instructions-only** — pure agent review; no scanners.

**Known gap (called out, not papered over):** there is no mature off-the-shelf
prompt-injection scanner. For agent builds the custom-rule check is a coarse net;
the *contextual* security agent carries the real weight. Do not represent scanner
coverage for agent builds as equivalent to code SAST.

## 5. Consequences

- **Positive:** zero licensing cost; no GitHub Advanced Security requirement;
  polyglot coverage; the frozen contract decouples tool choice from the agents, so
  a tool can be swapped without touching agent prompts or the orchestrator.
- **Negative / residual risk:** the prompt-injection gap (§4); the adapter is new
  code we maintain; OSS tools need their own ruleset/version pinning in CI to stay
  deterministic (a flaky/auto-updating ruleset would make the security wall
  non-reproducible — pin versions and rulesets).
- **Out of scope of this ADR:** the build-artifact repos and their CI pipelines do
  not exist yet and are R&D's plumbing. Adopting this decision later means: (a) the
  reusable GitHub Actions workflow template, (b) the normalizer adapter + tests.
  Neither touches the orchestrator spine.

## 6. Resolved sub-decisions and remaining gate

Resolved (this revision):

- **SCA tool → Trivy** (not OSV-Scanner). Trivy consolidates dependency CVEs and
  IaC misconfig in one binary; OSV-Scanner is SCA-only and would still need a
  separate misconfig story. Gitleaks remains the dedicated secrets tool (cleaner
  `type/file/line/detector` output than Trivy's secret mode).
- **Bandit → dropped from the default, kept as a per-repo opt-in.** Semgrep's
  Python ruleset already covers the high-value Bandit checks; running both would
  force cross-tool dedup in the normalizer for marginal gain. A documented hook
  lets a Python-heavy artifact enable Bandit when justified.
- **Version-pinning → mandatory.** The wall is non-bypassable and must be
  *reproducible*: pin tool versions **and** ruleset versions/commit SHAs (Semgrep
  community packs auto-update upstream otherwise) in the shared workflow template,
  not per-repo. Pair the pin with a scheduled monthly refresh (Renovate/Dependabot
  on the template) so pins stay current without silent drift — pinned-but-updated,
  not frozen.

Free-tier caveat (tracked, not blocking):

- **Semgrep** OSS engine + community rules are free; the Pro engine and some
  advanced rules are paid. This version stays on the free OSS engine + community
  rules. Revisit only if coverage gaps are demonstrated.

Remaining gate:

- **R&D co-sign required** before this moves from Proposed to Accepted —
  Architecture §4 puts scanner tooling and CI plumbing under R&D. This is now the
  only open item.

## 7. Alternatives considered

- **GitHub-native (CodeQL + Dependabot/Dependency Review + native secret
  scanning).** Tighter integration, but requires paid **GitHub Advanced Security**
  on private repos — rejected on cost and vendor-neutrality grounds.
- **Minimal Python-only (Bandit + pip-audit + Gitleaks).** Lightest to stand up,
  but Python-only SAST/SCA leaves polyglot artifacts (e.g. JS) uncovered —
  rejected as too narrow. (Bandit survives as a per-repo opt-in; see §6.)
- **OSV-Scanner for SCA.** Cleaner, curated CVE feed, but dependency-only — no
  misconfig coverage, so it would not consolidate. Rejected in favor of Trivy (§6).
