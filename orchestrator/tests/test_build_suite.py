from app.agents import build_manifest_schema, load_build_spec
from app.evals.build_assertions import check_build
from app.evals.loader import load_build_fixtures
from app.evals.runner import run_build_suite_replay
from app.invocation import OutputMode, Tier


def test_build_spec_loads():
    spec = load_build_spec()
    assert spec.name == "build-agent"
    assert spec.tier is Tier.HIGH
    assert spec.output_mode is OutputMode.STRUCTURED
    assert "director_responses" in spec.block_names
    assert spec.output_schema["title"] == "BuildManifest"


def test_build_replay_all_green():
    suite = run_build_suite_replay(build_manifest_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"build replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"B1", "B4", "B5"} <= ids
    assert {"B_neg_self_grade", "B_neg_artifact_avenue", "B_neg_ac_invented"} <= ids


def test_build_negatives_truly_fail_engine():
    by_id = {f.case_id: f for f in load_build_fixtures()}
    for neg in ("B_neg_self_grade", "B_neg_artifact_avenue", "B_neg_ac_invented"):
        fx = by_id[neg]
        assert not check_build(fx, fx.recorded_output, build_manifest_schema()).passed
