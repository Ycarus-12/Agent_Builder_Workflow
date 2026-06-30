"""Verify the OpenRouter gateway setup: `python -m app.check_gateway`.

Loads the gateway config from the environment, builds the OpenRouter adapter, and
makes one tiny real completion to confirm the key, base URL, and model all work.
Prints OK with the model's reply, or a clear error. Makes a real API call, so it
needs OPENROUTER_API_KEY set; it does not touch Airtable/Resend.
"""

from __future__ import annotations

import sys

from .composition import default_model_map
from .config import load_gateway_config
from .invocation import AgentSpec, InputEnvelope, OutputMode, Tier
from .ports.gateway import GatewayError, OpenRouterGateway

_CHECK_AGENT = "conn-check"


def main() -> int:
    config = load_gateway_config()
    if not config.has_key:
        print("OPENROUTER_API_KEY is not set. Export your OpenRouter key and retry:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        return 1

    # Build the gateway with the normal per-agent model map plus a tiny check agent.
    models = {**default_model_map(config), _CHECK_AGENT: (config.conversation_model, 20)}
    gateway = OpenRouterGateway(config, models)

    spec = AgentSpec(
        name=_CHECK_AGENT, version="0", commit_hash="0", tier=Tier.MID,
        output_mode=OutputMode.PROSE, block_names=("ping",),
        system_prompt="You are a connectivity check. Reply with exactly: ok",
    )
    envelope = InputEnvelope(spec=spec, blocks={"ping": "ping"})

    print(f"Base URL : {config.base_url}")
    print(f"Model    : {config.conversation_model}")
    try:
        reply = gateway.complete(envelope)
    except GatewayError as exc:
        print(f"FAILED   : {exc}")
        return 1
    print(f"Reply    : {reply.strip()[:80]!r}")
    print("OK — OpenRouter gateway is reachable and the key works.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
