"""FastAPI surface for the orchestrator spine.

Health/introspection probes plus the Director gate console (app.console): the
server-rendered UI where the Director acts on the pipeline's stop points. The
console holds no state between requests — each page rehydrates a runner from the
datastore, so it is safe behind Connect's multi-process/ephemeral hosting.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .auth import router as auth_router
from .console import router as console_router
from .intake_console import router as intake_router
from .state_machine import DIRECTOR_GATES, Stage

app = FastAPI(title="Tool-Request Orchestrator", version="0.1.0")
# Signed-cookie sessions for the local username/password auth. SESSION_SECRET must
# be set in any shared/production deployment; the dev fallback keeps local runs working.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-only-insecure-session-secret"),
)
app.include_router(auth_router)
app.include_router(console_router)
app.include_router(intake_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "contract": "orchestrator-contract v1.1.0"}


@app.get("/stages")
def stages() -> dict[str, object]:
    """Expose the pipeline stages and the Director gate stop-points."""
    return {
        "stages": [s.value for s in Stage],
        "director_gates": [s.value for s in DIRECTOR_GATES],
    }
