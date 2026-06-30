"""Prompt loader: build AgentSpecs from the real agent artifacts in agents/.

Each agent .md is `--- frontmatter ---`, then an artifact-note blockquote, then a
`---` divider, then the system-prompt body. The body below that final divider is
what the model sees; the frontmatter (version, etc.) is tooling metadata and is
NOT sent to the model. Block names / tier / output mode come from the orchestrator
contract, not the prompt, so they are declared here per agent.
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml

from .invocation import AgentSpec, OutputMode, Tier

# orchestrator/ -> repo root -> agents/ , and the vendored intake schema.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _REPO_ROOT / "agents"
_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

INTAKE_CONVERSATION_FILE = "intake-conversation_v1_0.md"
INTAKE_EXTRACTION_FILE = "intake-extraction_v1_0.md"
STACK_CHECK_FILE = "stack-check_v1_0.md"
TRIAGE_FILE = "triage-recommender_v1_0.md"
COST_ROM_FILE = "cost-estimation-rom_v1_1.md"
COST_DEEPDIVE_FILE = "cost-estimation-deepdive_v1_0.md"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, remainder_after_frontmatter)."""
    if not text.lstrip().startswith("---"):
        return {}, text
    # Drop everything up to the first '---', then split on the closing '---'.
    body = text.split("---", 1)[1]
    fm_raw, _, remainder = body.partition("\n---")
    front = yaml.safe_load(fm_raw) or {}
    return front, remainder


def _system_prompt_body(remainder: str) -> str:
    """From the post-frontmatter remainder, drop the artifact-note blockquote and
    return the system-prompt body (everything after the next '---' divider)."""
    lines = remainder.splitlines()
    divider_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            divider_idx = i
            break
    body_lines = lines[divider_idx + 1 :] if divider_idx is not None else lines
    return "\n".join(body_lines).strip()


def load_agent_artifact(filename: str) -> tuple[dict, str]:
    """Parse one agent file into (frontmatter, system_prompt_body)."""
    text = (_AGENTS_DIR / filename).read_text(encoding="utf-8")
    front, remainder = _split_frontmatter(text)
    return front, _system_prompt_body(remainder)


@lru_cache(maxsize=1)
def repo_commit_hash() -> str:
    """Short git commit hash for call-site traceability (§3.4). 'unknown' off-tree."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - environment dependent
        return "unknown"


@lru_cache(maxsize=1)
def intake_record_schema() -> dict:
    return json.loads((_SCHEMA_DIR / "intake_record.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def stack_check_finding_schema() -> dict:
    return json.loads((_SCHEMA_DIR / "stack_check_finding.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def triage_output_schema() -> dict:
    return json.loads((_SCHEMA_DIR / "triage_output.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def cost_rom_schema() -> dict:
    return json.loads((_SCHEMA_DIR / "cost_rom.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def cost_deepdive_schema() -> dict:
    return json.loads((_SCHEMA_DIR / "cost_deepdive.json").read_text(encoding="utf-8"))


def load_intake_conversation_spec() -> AgentSpec:
    front, body = load_agent_artifact(INTAKE_CONVERSATION_FILE)
    return AgentSpec(
        name="intake-conversation",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.MID,
        output_mode=OutputMode.PROSE,
        block_names=("requestor_identity", "conversation"),
        system_prompt=body,
    )


def load_intake_extraction_spec() -> AgentSpec:
    front, body = load_agent_artifact(INTAKE_EXTRACTION_FILE)
    return AgentSpec(
        name="intake-extraction",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.SLM,
        output_mode=OutputMode.STRUCTURED,
        block_names=("Auto-filled", "TRANSCRIPT"),
        output_schema=intake_record_schema(),
        system_prompt=body,
    )


def load_stack_check_spec() -> AgentSpec:
    # stack-check also calls the registry_search tool mid-invocation (handled by the
    # runtime tool-loop); this spec covers its final forced structured finding.
    front, body = load_agent_artifact(STACK_CHECK_FILE)
    return AgentSpec(
        name="stack-check",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.MID,
        output_mode=OutputMode.STRUCTURED,
        block_names=("intake_record",),
        output_schema=stack_check_finding_schema(),
        system_prompt=body,
    )


def load_triage_spec() -> AgentSpec:
    front, body = load_agent_artifact(TRIAGE_FILE)
    return AgentSpec(
        name="triage-recommender",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.HIGH,
        output_mode=OutputMode.STRUCTURED,
        block_names=("intake_record", "transcript", "stack_check_result"),
        output_schema=triage_output_schema(),
        system_prompt=body,
    )


def load_cost_rom_spec() -> AgentSpec:
    front, body = load_agent_artifact(COST_ROM_FILE)
    return AgentSpec(
        name="cost-estimation-rom",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.SLM,
        output_mode=OutputMode.STRUCTURED,
        block_names=("INTAKE RECORD", "OPTION LIST"),
        output_schema=cost_rom_schema(),
        system_prompt=body,
    )


def load_cost_deepdive_spec() -> AgentSpec:
    front, body = load_agent_artifact(COST_DEEPDIVE_FILE)
    return AgentSpec(
        name="cost-estimation-deepdive",
        version=str(front.get("version", "0.0.0")),
        commit_hash=repo_commit_hash(),
        tier=Tier.HIGH,
        output_mode=OutputMode.STRUCTURED,
        block_names=("intake_extract", "transcript", "stack_check_finding", "rom_output", "selected_options"),
        output_schema=cost_deepdive_schema(),
        system_prompt=body,
    )
