"""Eval suite runner — replay (every-commit gate) and live (key-gated) modes."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..intake import ConversationSession, build_extraction_envelope, run_conversation_turn
from ..invocation import AgentSpec
from ..ports.gateway import ModelGateway
from ..ports.identity import RequestorIdentity
from .assertions import CaseResult, check_conversation, check_extraction
from .loader import (
    BuildFixture,
    ConversationFixture,
    CostDeepDiveFixture,
    CostRomFixture,
    ExtractionFixture,
    StackCheckFixture,
    TriageFixture,
    QaFixture,
    SecurityFixture,
    load_build_fixtures,
    load_conversation_fixtures,
    load_cost_deepdive_fixtures,
    load_cost_rom_fixtures,
    load_extraction_fixtures,
    load_qa_fixtures,
    load_security_gov_fixtures,
    load_security_vuln_fixtures,
    load_stack_check_fixtures,
    load_triage_fixtures,
)
from .build_assertions import check_build
from .qa_assertions import check_qa
from .security_assertions import check_security
from .deepdive_assertions import check_deepdive
from .rom_assertions import check_rom
from .stack_check_assertions import check_stack_check
from .triage_assertions import check_triage


@dataclass
class SuiteResult:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.passed]

    @property
    def ok(self) -> bool:
        return not self.failed


def _apply_expect(fixture, result: CaseResult) -> CaseResult:
    """Negative fixtures (expect_result='fail') must be REJECTED by the engine; if
    they pass clean, the gate failed to bite."""
    if fixture.expect_result == "fail":
        if result.passed:
            return CaseResult(
                fixture.case_id,
                passed=False,
                failures=["expected fixture to FAIL its assertions, but it passed (gate did not bite)"],
            )
        return CaseResult(fixture.case_id, passed=True)
    return result


# -- extraction -------------------------------------------------------------
def run_extraction_replay(fixtures: list[ExtractionFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_extraction(fx, fx.recorded_output, schema)))
    return results


def run_extraction_live(
    fixtures: list[ExtractionFixture], gateway: ModelGateway, spec: AgentSpec, schema: dict
) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.replay_only or fx.expect_result == "fail":
            continue  # negatives are replay-only; can't force a live model to misbehave
        env = build_extraction_envelope(spec, auto_filled=fx.auto_filled, transcript=fx.transcript)
        raw = gateway.complete(env)
        results.append(check_extraction(fx, raw, schema))
    return results


# -- conversation -----------------------------------------------------------
def run_conversation_replay(fixtures: list[ConversationFixture]) -> list[CaseResult]:
    return [check_conversation(fx, fx.recorded_responses) for fx in fixtures]


def run_conversation_live(
    fixtures: list[ConversationFixture], gateway: ModelGateway, spec: AgentSpec
) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.replay_only:
            continue
        identity = RequestorIdentity(
            fx.auto_filled.get("requestor", "Test User"), fx.auto_filled.get("team", "Test Team")
        )
        session = ConversationSession(session_id=fx.case_id, identity=identity)
        responses = []
        for turn in fx.turns:
            result = run_conversation_turn(gateway, spec, session, turn["content"])
            responses.append(result.raw_agent_response)
            if result.marker.fired:
                break
        results.append(check_conversation(fx, responses))
    return results


# -- stack-check ------------------------------------------------------------
def run_stack_check_replay(fixtures: list[StackCheckFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_stack_check(fx, fx.recorded_output, schema)))
    return results


# -- triage -----------------------------------------------------------------
def run_triage_replay(fixtures: list[TriageFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_triage(fx, fx.recorded_output, schema)))
    return results


# -- top level --------------------------------------------------------------
def run_intake_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_extraction_replay(load_extraction_fixtures(), schema)
    suite.cases += run_conversation_replay(load_conversation_fixtures())
    return suite


def run_cost_rom_replay(fixtures: list[CostRomFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_rom(fx, fx.recorded_output, schema)))
    return results


def run_cost_rom_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_cost_rom_replay(load_cost_rom_fixtures(), schema)
    return suite


def run_security_suite_replay(vuln_schema: dict, gov_schema: dict) -> SuiteResult:
    suite = SuiteResult()
    for fx in load_security_vuln_fixtures():
        if fx.recorded_output is None:
            suite.cases.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        suite.cases.append(_apply_expect(fx, check_security(fx, fx.recorded_output, vuln_schema)))
    for fx in load_security_gov_fixtures():
        if fx.recorded_output is None:
            suite.cases.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        suite.cases.append(_apply_expect(fx, check_security(fx, fx.recorded_output, gov_schema)))
    return suite


def run_qa_replay(fixtures: list[QaFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_qa(fx, fx.recorded_output, schema)))
    return results


def run_qa_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_qa_replay(load_qa_fixtures(), schema)
    return suite


def run_build_replay(fixtures: list[BuildFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_build(fx, fx.recorded_output, schema)))
    return results


def run_build_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_build_replay(load_build_fixtures(), schema)
    return suite


def run_cost_deepdive_replay(fixtures: list[CostDeepDiveFixture], schema: dict) -> list[CaseResult]:
    results = []
    for fx in fixtures:
        if fx.recorded_output is None:
            results.append(CaseResult(fx.case_id, False, ["no recorded_output for replay mode"]))
            continue
        results.append(_apply_expect(fx, check_deepdive(fx, fx.recorded_output, schema)))
    return results


def run_cost_deepdive_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_cost_deepdive_replay(load_cost_deepdive_fixtures(), schema)
    return suite


def run_stack_check_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_stack_check_replay(load_stack_check_fixtures(), schema)
    return suite


def run_triage_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_triage_replay(load_triage_fixtures(), schema)
    return suite


def run_intake_suite_live(
    schema: dict, gateway: ModelGateway, conversation_spec: AgentSpec, extraction_spec: AgentSpec
) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_extraction_live(load_extraction_fixtures(), gateway, extraction_spec, schema)
    suite.cases += run_conversation_live(load_conversation_fixtures(), gateway, conversation_spec)
    return suite
