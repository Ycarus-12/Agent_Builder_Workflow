from app.agents import cost_deepdive_schema, load_cost_deepdive_spec
from app.evals.deepdive_assertions import check_deepdive
from app.evals.loader import load_cost_deepdive_fixtures
from app.evals.runner import run_cost_deepdive_suite_replay
from app.invocation import OutputMode, Tier


def test_cost_deepdive_spec_loads():
    spec = load_cost_deepdive_spec()
    assert spec.name == "cost-estimation-deepdive"
    assert spec.tier is Tier.HIGH
    assert spec.output_mode is OutputMode.STRUCTURED
    assert spec.block_names == (
        "intake_extract", "transcript", "stack_check_finding", "rom_output", "selected_options",
    )
    assert spec.output_schema["title"] == "CostEstimationDeepDive"


def test_deepdive_replay_all_green():
    suite = run_cost_deepdive_suite_replay(cost_deepdive_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"deepdive replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"D1", "D3"} <= ids
    assert {"D_neg_order", "D_neg_range", "D_neg_reco_not_selected"} <= ids


def test_deepdive_negatives_truly_fail_engine():
    by_id = {f.case_id: f for f in load_cost_deepdive_fixtures()}
    for neg in ("D_neg_order", "D_neg_range", "D_neg_reco_not_selected"):
        fx = by_id[neg]
        assert not check_deepdive(fx, fx.recorded_output, cost_deepdive_schema()).passed
