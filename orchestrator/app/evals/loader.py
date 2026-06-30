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


@dataclass(frozen=True)
class CostDeepDiveFixture:
    case_id: str
    description: str
    selected_options: list[dict]
    assertions: dict
    intake_extract: dict = field(default_factory=dict)
    transcript: str = ""
    stack_check_finding: dict = field(default_factory=dict)
    rom_output: dict = field(default_factory=dict)
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class BuildFixture:
    case_id: str
    description: str
    build_type: str
    acceptance_criteria: list[str]
    spec_context: dict
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class QaFixture:
    case_id: str
    description: str
    build_type: str
    acceptance_criteria: list[str]
    oracle: dict
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class SecurityFixture:
    case_id: str
    description: str
    kind: str            # "vuln" | "gov"
    assertions: dict
    data_sensitivity: str | None = None   # governance only
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class PortfolioFixture:
    case_id: str
    description: str
    clusters: list[dict]
    pseudo_agent_usage: list[dict]
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


@dataclass(frozen=True)
class RegistryMaintenanceFixture:
    case_id: str
    description: str
    run_context: dict
    drift_report: list[dict]
    affected_records: list[str]
    oracle: dict
    assertions: dict
    expect_result: str = "pass"
    recorded_output: str | None = None
    replay_only: bool = False


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_portfolio_fixtures(directory: Path | None = None) -> list[PortfolioFixture]:
    directory = directory or (_FIXTURES_DIR / "portfolio")
    out: list[PortfolioFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            PortfolioFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                clusters=d.get("clusters", []),
                pseudo_agent_usage=d.get("pseudo_agent_usage", []),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_registry_maintenance_fixtures(directory: Path | None = None) -> list[RegistryMaintenanceFixture]:
    directory = directory or (_FIXTURES_DIR / "registry_maintenance")
    out: list[RegistryMaintenanceFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            RegistryMaintenanceFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                run_context=d.get("run_context", {}),
                drift_report=d.get("drift_report", []),
                affected_records=d.get("affected_records", []),
                oracle=d.get("oracle", {}),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def _load_security_fixtures(directory: Path, kind: str) -> list[SecurityFixture]:
    out: list[SecurityFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            SecurityFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                kind=kind,
                assertions=d.get("assertions", {}),
                data_sensitivity=d.get("data_sensitivity"),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_security_vuln_fixtures(directory: Path | None = None) -> list[SecurityFixture]:
    return _load_security_fixtures(directory or (_FIXTURES_DIR / "security_vuln"), "vuln")


def load_security_gov_fixtures(directory: Path | None = None) -> list[SecurityFixture]:
    return _load_security_fixtures(directory or (_FIXTURES_DIR / "security_gov"), "gov")


def load_qa_fixtures(directory: Path | None = None) -> list[QaFixture]:
    directory = directory or (_FIXTURES_DIR / "functional_qa")
    out: list[QaFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            QaFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                build_type=d.get("build_type", ""),
                acceptance_criteria=d.get("acceptance_criteria", []),
                oracle=d.get("oracle", {}),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_build_fixtures(directory: Path | None = None) -> list[BuildFixture]:
    directory = directory or (_FIXTURES_DIR / "build")
    out: list[BuildFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            BuildFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                build_type=d.get("build_type", ""),
                acceptance_criteria=d.get("acceptance_criteria", []),
                spec_context=d.get("spec_context", {}),
                assertions=d.get("assertions", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


def load_cost_deepdive_fixtures(directory: Path | None = None) -> list[CostDeepDiveFixture]:
    directory = directory or (_FIXTURES_DIR / "deepdive")
    out: list[CostDeepDiveFixture] = []
    for path in sorted(directory.glob("*.yaml")):
        d = _load_yaml(path)
        out.append(
            CostDeepDiveFixture(
                case_id=d["case_id"],
                description=d.get("description", ""),
                selected_options=d.get("selected_options", []),
                assertions=d.get("assertions", {}),
                intake_extract=d.get("intake_extract", {}),
                transcript=d.get("transcript", ""),
                stack_check_finding=d.get("stack_check_finding", {}),
                rom_output=d.get("rom_output", {}),
                expect_result=d.get("expect_result", "pass"),
                recorded_output=d.get("recorded_output"),
                replay_only=d.get("replay_only", False),
            )
        )
    return out


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
