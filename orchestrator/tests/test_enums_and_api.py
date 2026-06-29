from fastapi.testclient import TestClient

from app.api import app
from app.enums import (
    SIGNOFF_MARKER,
    BuildType,
    DataSensitivity,
    Engine,
    Outcome,
    Route,
    Status,
    Support,
    Weight,
)


def test_enums_are_verbatim():
    # Guards against accidental rename/recase of the locked vocabulary (context §5).
    assert [r.value for r in Route] == ["configure", "build", "buy"]
    assert [o.value for o in Outcome] == [
        "route_elsewhere", "dont_build", "configure", "process_training_fix", "buy", "build",
    ]
    assert [b.value for b in BuildType] == [
        "code", "agent_creation", "config_applied", "config_instructions",
    ]
    assert [e.value for e in Engine] == ["ai", "deterministic"]
    assert [w.value for w in Weight] == ["light", "heavy"]
    assert [d.value for d in DataSensitivity] == [
        "none", "internal", "customer", "financial", "regulated", "unspecified",
    ]
    assert [s.value for s in Support] == ["native", "configurable", "not_supported"]
    assert [s.value for s in Status] == [
        "Planned", "In build", "In pilot", "In use", "Deprecated",
    ]
    assert SIGNOFF_MARKER == "[[INTAKE_SIGNOFF_CONFIRMED]]"


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_stages_endpoint_lists_director_gates():
    client = TestClient(app)
    body = client.get("/stages").json()
    assert "gate_1a" in body["director_gates"]
    assert "deploy_and_register" in body["stages"]
