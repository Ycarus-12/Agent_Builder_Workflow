import pytest

from app.evals.rubric import RUBRICS, FakeJudge, grade

BUILD = "build-agent"
_DIMS = [d.name for d in RUBRICS[BUILD]]


def _all(score: int) -> dict[str, int]:
    return {d: score for d in _DIMS}


def test_median_pass_all_dimensions():
    judge = FakeJudge([_all(4), _all(4), _all(4)])
    result = grade(judge, BUILD, "subject", runs=3)
    assert result.passed
    assert all(m == 4 for m in result.medians.values())


def test_one_dimension_below_bar_fails():
    runs = [_all(4), _all(4), _all(4)]
    for r in runs:
        r["no_self_grade"] = 2
    result = grade(FakeJudge(runs), BUILD, "subject", runs=3)
    assert not result.passed
    assert result.medians["no_self_grade"] == 2


def test_median_damps_variance():
    # no_self_grade scored 5,1,3 across runs -> median 3 (passes the bar)
    runs = [_all(4), _all(4), _all(4)]
    runs[0]["no_self_grade"] = 5
    runs[1]["no_self_grade"] = 1
    runs[2]["no_self_grade"] = 3
    result = grade(FakeJudge(runs), BUILD, "subject", runs=3)
    assert result.medians["no_self_grade"] == 3
    assert result.passed


def test_baseline_regression_detected():
    runs = [_all(4), _all(4), _all(4)]
    for r in runs:
        r["ac_traceability"] = 2
    result = grade(FakeJudge(runs), BUILD, "subject", runs=3)
    baseline = {d: 4.0 for d in _DIMS}
    regressed = result.regressed_vs(baseline)
    assert regressed == ["ac_traceability"]  # dropped 4 -> 2 (> 1)


def test_small_drop_within_tolerance_not_flagged():
    runs = [_all(3), _all(3), _all(3)]  # 4 -> 3 is a drop of 1, within tolerance
    result = grade(FakeJudge(runs), BUILD, "subject", runs=3)
    assert result.regressed_vs({d: 4.0 for d in _DIMS}) == []


def test_unknown_agent_has_no_rubric():
    with pytest.raises(KeyError):
        grade(FakeJudge([{}]), "stack-check", "subject")
