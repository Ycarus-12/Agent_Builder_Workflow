"""Shared Jinja2 templates instance (used by the console, intake, and auth routers)."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
