"""Posit Connect Cloud entrypoint (ASGI).

Connect Cloud deploys the whole repository and serves the `app` object in the
primary file. The orchestrator lives in `orchestrator/app`; put that directory on
the import path and re-export the FastAPI app. All config/secrets come from
Connect-managed environment variables at runtime (nothing is hardcoded).

Connect form:  Primary file = connect_app.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator"))

from app.api import app  # noqa: E402  -- the ASGI app Connect serves

__all__ = ["app"]
