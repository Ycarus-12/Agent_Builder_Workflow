# Orchestrator spine

The deterministic application layer for the agentic tool-request workflow —
the implementation of `docs/orchestrator-contract_v1_1.md`. It sequences stages,
attaches context per rule, enforces the human gates, validates structured agent
outputs and retries, applies the sensitivity overlay, and logs everything.

**It holds no judgment.** Sequencing, routing, gating, and logging are code;
judgment lives only in the agents. Every external dependency is a seam behind an
interface in `app/ports/`, so nothing hardwires a provider and the whole spine
runs and tests offline on in-memory fakes.

## Layout

| Module | Contract § | Responsibility |
|---|---|---|
| `app/enums.py` | context §5 | Canonical vocabulary, verbatim |
| `app/state_machine.py` | §2 | Pipeline stages, analysis sub-pipeline, gates, stop list |
| `app/invocation.py` | §3.1, §3.3 | Input envelope (XML/bracket), output modes |
| `app/context_policy.py` | §3.2 | Deterministic per-stage context attachment |
| `app/retry_loop.py` | §5 | Validate-and-retry, escalation on exhaustion |
| `app/sensitivity.py` | §6 | `unspecified` = sensitive-until-confirmed |
| `app/markers.py` | §4.3 | Deterministic sign-off marker detection |
| `app/intake.py` | §4 | Conversation loop + one-shot extraction handoff |
| `app/logging_audit.py` | §8 | Event log with redaction by sensitivity |
| `app/ports/` | §1, tool decisions | Model gateway / datastore / emailer / identity seams (+ fakes) |
| `app/api.py` | — | FastAPI skeleton (health + stage introspection) |

## Run

```bash
cd orchestrator
pip install -r requirements.txt
pytest -q
uvicorn app.api:app --reload   # optional: serve the skeleton API
```

## Scope (this phase)

In: the deterministic core + seams-as-fakes + unit tests + a fake end-to-end
flow. Deferred (per contract §9 and the build order): live intake wiring through
the gateway (Phase 3), real Airtable/Resend/SSO/OpenRouter integrations, the eval
harness (Phase 4), queueing/parallelism, and production gateway selection.
