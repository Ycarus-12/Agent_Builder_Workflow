"""AI Enabler login: required for the console, role-gated, and bad creds rejected.
Requestors are guests (no login) — covered in test_intake_console."""

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.composition import build_services
from app.console import get_services


@pytest.fixture()
def svc():
    s = build_services("offline")
    app.dependency_overrides[get_services] = lambda: s
    yield s
    app.dependency_overrides.clear()


def test_unauthenticated_redirected_to_login(svc):
    r = TestClient(app).get("/requests", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_bad_credentials_rejected(svc):
    r = TestClient(app).post("/login", data={"username": "enabler", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 303 and "error" in r.headers["location"]


def test_enabler_login_reaches_console_and_lands_on_requests(svc):
    c = TestClient(app)
    r = c.post("/login", data={"username": "enabler", "password": "enabler"}, follow_redirects=False)
    assert r.headers["location"] == "/requests"
    assert c.get("/requests").status_code == 200


def test_logout_clears_session(svc):
    c = TestClient(app)
    c.post("/login", data={"username": "enabler", "password": "enabler"})
    c.get("/logout")
    assert c.get("/requests", follow_redirects=False).status_code == 303
