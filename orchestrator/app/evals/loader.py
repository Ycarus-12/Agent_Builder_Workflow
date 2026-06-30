"""Fixture loading (contract §7.1).

One YAML file per case. Conversation fixtures (C*) carry scripted requestor turns
and, for replay mode, the agent's recorded responses. Extraction fixtures (E*)
carry the transcript + auto-fill and, for replay mode, the recorded JSON output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


@dataclass(frozen=True)
class ExtractionFixture:
    case_id: str
    description: str
    auto_filled: dict
    transcript: str
    assertions: dict
    expect_result: str = "pass"          # "pass" | "fail" (negative fixtures)
    recorded_output: str | None = None   # golden raw agent output for replay mode
    replay_only: bool = False            # negatives can't be produced live


@dataclass(frozen=True)
class ConversationFixture:
    case_id: str
    description: str
    auto_filled: dict
    turns: list[dict]
    expected_terminal_state: str
    recorded_responses: list[str] = field(default_factory=list)
    replay_only: bool = False


@dataclass(frozen=True)
class StackCheckFixture:
    case_id: str
    description: str
    intake_record: dict
    registry_mock: dict
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class TriageFixture:
    case_id: str
    description: str
    intake_record: dict
    transcript: str
    stack_check_result: dict
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class CostRomFixture:
    case_id: str
    description: str
    intake_record: dict
    option_list: list[dict]
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_cost_rom_fixtures(directory: Path | None = None) -> list[CostRomFixture]:
    directory = directory or (_FIXTURES_DIR / "rom")
    out: list[CostRomFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            CostRomFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                intake_record=d.get("intake_record", {}),
                option_list=d.get("option_list", []),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_extraction_fixtures(directory: Path | None = None) -> list[ExtractionFixture]:
    directory = directory or (_FIXTURES_DIR / "extraction")
    out: list[ExtractionFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            ExtractionFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                auto_filled=d.get("auto_filled", {}),
                transcript=d.get("transcript", ""),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_stack_check_fixtures(directory: Path | None = None) -> list[StackCheckFixture]:
    directory = directory or (_FIXTURES_DIR / "stack_check")
    out: list[StackCheckFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            StackCheckFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                intake_record=d.get("intake_record", {}),
                registry_mock=d.get("registry_mock", {}),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_triage_fixtures(directory: Path | None = None) -> list[TriageFixture]:
    directory = directory or (_FIXTURES_DIR / "triage")
    out: list[TriageFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            TriageFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                intake_record=d.get("intake_record", {}),
                transcript=d.get("transcript", ""),
                stack_check_result=d.get("stack_check_result", {}),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_conversation_fixtures(directory: Path | None = None) -> list[ConversationFixture]:
    directory = directory or (_FIXTURES_DIR / "conversation")
    out: list[ConversationFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            ConversationFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                auto_filled=d.get("auto_filled", {}),
                turns=d.get("turns", []),
                expected_terminal_state=d["expected_terminal_state"],
                recorded_responses=d.get("recorded_responses", []),
                replay_only=d.get("replay_only", False),
            )
        )
    return out
