from app.agents import cost_rom_schema, load_cost_rom_spec
from app.evals.loader import load_cost_rom_fixtures
from app.evals.rom_assertions import check_rom
from app.evals.runner import run_cost_rom_suite_replay
from app.invocation import OutputMode, Tier


def test_cost_rom_spec_loads():
    spec = load_cost_rom_spec()
    assert spec.name == "cost-estimation-rom"
    assert spec.tier is Tier.SLM
    assert spec.output_mode is OutputMode.STRUCTURED
    assert spec.block_names == ("INTAKE RECORD", "OPTION LIST")
    assert spec.output_schema["title"] == "CostEstimationROM"


def test_rom_replay_all_green():
    suite = run_cost_rom_suite_replay(cost_rom_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"rom replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"R1", "R2", "R3"} <= ids
    assert {"R_neg_order", "R_neg_dollar", "R_neg_configure_runcost"} <= ids


def test_rom_negatives_truly_fail_engine():
    by_id = {f.case_id: f for f in load_cost_rom_fixtures()}
    for neg in ("R_neg_order", "R_neg_dollar", "R_neg_configure_runcost"):
        fx = by_id[neg]
        assert not check_rom(fx, fx.recorded_output, cost_rom_schema()).passed
