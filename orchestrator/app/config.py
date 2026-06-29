"""Env-driven configuration (CLAUDE.md: no secrets in code).

All provider details — base URL, API key, per-agent model ids, token ceilings —
come from the environment / Connect managed variables. Nothing here hardwires a
provider; production swaps the gateway by changing env, not code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# OpenRouter is the dev/test gateway (OpenAI-compatible API); BYOK Anthropic key.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Single-provider (Anthropic) to start; routed through OpenRouter's namespacing.
DEFAULT_CONVERSATION_MODEL = "anthropic/claude-sonnet-4.6"   # mid tier, live/streaming
DEFAULT_EXTRACTION_MODEL = "anthropic/claude-haiku-4.5"      # SLM tier, mechanical


@dataclass(frozen=True)
class GatewayConfig:
    base_url: str
    api_key: str | None
    conversation_model: str
    extraction_model: str
    conversation_max_tokens: int
    extraction_max_tokens: int
    # Optional OpenRouter attribution headers.
    http_referer: str | None = None
    app_title: str | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def load_gateway_config() -> GatewayConfig:
    """Build the gateway config from the environment.

    `OPENROUTER_API_KEY` is read but never required at import time — the spine and
    its tests run without it; only an actual live call needs it.
    """
    return GatewayConfig(
        base_url=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        conversation_model=os.environ.get("INTAKE_CONVERSATION_MODEL", DEFAULT_CONVERSATION_MODEL),
        extraction_model=os.environ.get("INTAKE_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL),
        conversation_max_tokens=int(os.environ.get("INTAKE_CONVERSATION_MAX_TOKENS", "1024")),
        extraction_max_tokens=int(os.environ.get("INTAKE_EXTRACTION_MAX_TOKENS", "2000")),
        http_referer=os.environ.get("OPENROUTER_HTTP_REFERER"),
        app_title=os.environ.get("OPENROUTER_APP_TITLE", "tool-request-orchestrator"),
    )
