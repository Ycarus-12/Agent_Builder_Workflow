"""Posit Connect Cloud entrypoint (FastAPI / ASGI).

Connect Cloud deploys the whole repository and serves the `app` object in the
primary file. The orchestrator lives in `orchestrator/app`; put that directory on
the import path and re-export the FastAPI app. All config/secrets come from
Connect-managed environment variables at runtime (nothing is hardcoded).

Connect publish settings:
    Framework / content type = FastAPI   (NOT Shiny — the Python default)
    Primary file             = connect_app.py
    Entrypoint               = connect_app:app
"""

import os
import sys

from fastapi import FastAPI  # explicit so the content type is detected as FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator"))

from app.api import app  # noqa: E402  -- the ASGI app Connect serves

assert isinstance(app, FastAPI)  # fail fast if the entrypoint ever stops being FastAPI

__all__ = ["app"]
