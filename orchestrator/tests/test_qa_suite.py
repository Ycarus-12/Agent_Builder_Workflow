from app.agents import load_functional_qa_spec, qa_verdict_schema
from app.evals.loader import load_qa_fixtures
from app.evals.qa_assertions import check_qa
from app.evals.runner import run_qa_suite_replay
from app.invocation import OutputMode, Tier


def test_functional_qa_spec_loads():
    spec = load_functional_qa_spec()
    assert spec.name == "functional-qa"
    assert spec.tier is Tier.HIGH
    assert spec.output_mode is OutputMode.STRUCTURED
    assert spec.block_names == ("build_manifest", "acceptance_criteria", "build_type")
    assert spec.output_schema["title"] == "QAVerdict"


def test_qa_replay_all_green():
    suite = run_qa_suite_replay(qa_verdict_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"qa replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"Q1", "Q2", "Q6", "Q7"} <= ids
    assert {"Q_neg_oracle", "Q_neg_security", "Q_neg_manifest"} <= ids


def test_qa_negatives_truly_fail_engine():
    by_id = {f.case_id: f for f in load_qa_fixtures()}
    for neg in ("Q_neg_oracle", "Q_neg_security", "Q_neg_manifest"):
        fx = by_id[neg]
        assert not check_qa(fx, fx.recorded_output, qa_verdict_schema()).passed
