"""The registry_search tool exposed to stack-check during its chat loop.

The tool definition (OpenAI-style function schema) plus the executor that binds it
to a RegistrySource and returns the flattened matches as JSON.
"""

from __future__ import annotations

import json

from .search import registry_search
from .source import RegistrySource

REGISTRY_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "registry_search",
        "description": (
            "Search the capability registry for capabilities that may cover the "
            "described need. Call exactly once with a natural-language query."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Natural-language description of the problem."},
                "systems_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional system names from systems_involved.",
                },
            },
        },
    },
}


def execute_registry_search(source: RegistrySource, arguments: dict) -> str:
    """Run registry_search with the model-supplied arguments; return JSON results."""
    matches = registry_search(
        source,
        query=arguments.get("query", ""),
        systems_filter=arguments.get("systems_filter"),
    )
    return json.dumps({"matches": matches})


def emit_tool(name: str, schema: dict) -> dict:
    """A forced-output tool whose parameters are the agent's declared schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Emit the final structured record matching the schema.",
            "parameters": schema,
        },
    }
