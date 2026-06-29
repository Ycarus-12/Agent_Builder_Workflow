"""Eval suite runner — replay (every-commit gate) and live (key-gated) modes."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..intake import ConversationSession, build_extraction_envelope, run_conversation_turn
from ..invocation import AgentSpec
from ..ports.gateway import ModelGateway
from ..ports.identity import RequestorIdentity
from .assertions import CaseResult, check_conversation, check_extraction
from .loader import (
    ConversationFixture,
    ExtractionFixture,
    load_conversation_fixtures,
    load_extraction_fixtures,
)


@dataclass
class SuiteResult:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.passed]

    @property
    def ok(self) -> bool:
        return not self.failed


def _apply_expect(fixture: ExtractionFixture, result: CaseResult) -> CaseResult:
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


# -- top level --------------------------------------------------------------
def run_intake_suite_replay(schema: dict) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_extraction_replay(load_extraction_fixtures(), schema)
    suite.cases += run_conversation_replay(load_conversation_fixtures())
    return suite


def run_intake_suite_live(
    schema: dict, gateway: ModelGateway, conversation_spec: AgentSpec, extraction_spec: AgentSpec
) -> SuiteResult:
    suite = SuiteResult()
    suite.cases += run_extraction_live(load_extraction_fixtures(), gateway, extraction_spec, schema)
    suite.cases += run_conversation_live(load_conversation_fixtures(), gateway, conversation_spec)
    return suite
