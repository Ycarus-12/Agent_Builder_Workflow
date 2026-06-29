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
