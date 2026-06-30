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
| `app/agents.py`, `app/runtime.py`, `app/run_intake.py` | §4 | Phase 3: real intake prompts wired end-to-end (CLI: `python -m app.run_intake --fake`) |
| `app/evals/`, `app/run_evals.py`, `evals/fixtures/` | §7 | Phase 4-5: eval harness — replay gate (`python -m app.run_evals --suite all`) + key-gated live mode |
| `app/registry/` | §3, Appendix C | Phase 5: registry_search infra (source seam, flatten layer, deterministic search) for stack-check |
| `app/evals/stack_check_assertions.py`, `triage_assertions.py` | §7 | Phase 5: stack-check + triage eval suites (replay-gated) |

## Run

```bash
cd orchestrator
pip install -r requirements.txt
pytest -q
uvicorn app.api:app --reload   # the console + intake UI
```

## Live model calls via OpenRouter (dev/test)

The model seam ships two adapters: an offline fake and `OpenRouterGateway`
(OpenRouter + your BYOK Anthropic key). Each seam picks its mode from the
environment — `ORCHESTRATOR_MODE` is the baseline, and `GATEWAY_MODE` /
`DATASTORE_MODE` / `EMAILER_MODE` override it per seam. So you can run **real
model calls locally with in-memory storage/email** — no Airtable/Resend needed:

```bash
cp .env.example .env            # then edit
export OPENROUTER_API_KEY=sk-or-...
export GATEWAY_MODE=live         # ORCHESTRATOR_MODE stays offline

python -m app.check_gateway      # one tiny real call to verify the key works
uvicorn app.api:app --reload     # now agents run through OpenRouter
```

`check_gateway` prints the base URL, model, and the model's reply (or a clear
error). See `.env.example` for the full variable list (models, Airtable, Resend,
auth, notification links).

### Secrets on Posit Connect Cloud

No API key lives in the code or the repo — every secret is read via `os.environ`
(`config.py`). Locally that's a gitignored `.env`. **On Connect, don't deploy a
`.env`:** set the same variable names as encrypted **Environment Variables /
Secrets** on the content's **Advanced** settings tab. Connect stores them
encrypted and decrypts them only when the process starts, so nothing sensitive is
ever in the deployed bundle.

## Deploy to Posit Connect Cloud (Shiny)

Connect Cloud's GitHub publish supports Shiny (not FastAPI), so the UI ships as two
**Shiny for Python** apps at the repo root that reuse the orchestrator backend
unchanged (`app.shiny_logic`). Publish them as **two separate contents**:

| Content | Primary file | Access | Audience |
|---|---|---|---|
| Intake | `intake_app.py` | **Public** | Guests log requests (no login) |
| Console | `console_app.py` | **Restricted to you** | AI Enabler — Connect handles the login |

For each: Publish → From GitHub → **Shiny** → repo `Ycarus-12/Agent_Builder_Workflow`,
branch `main`, primary file as above, Python 3.11. Set the same env vars (Advanced
tab) on **both** so they share one backend — at minimum `ORCHESTRATOR_MODE`/
`GATEWAY_MODE=live` + `OPENROUTER_API_KEY`, and `DATASTORE_MODE=live` + Airtable
(so both contents see the same requests). Theming comes from `_brand.yml` (Posit
Design System). The local FastAPI app under `orchestrator/app` stays for dev/tests;
`shiny run intake_app.py` runs an app locally.

## Scope (this phase)

In: the deterministic core + seams-as-fakes + unit tests + a fake end-to-end
flow. Deferred (per contract §9 and the build order): live intake wiring through
the gateway (Phase 3), real Airtable/Resend/SSO/OpenRouter integrations, the eval
harness (Phase 4), queueing/parallelism, and production gateway selection.
