"""registry_search — the one tool stack-check calls (deterministic, dev/test).

Token-overlap match over the flattened registry: a capability is a candidate when
the query (and optional systems filter) shares meaningful tokens with its statement,
record name, or category. Returns flattened matches ranked by overlap. A young/sparse
registry legitimately returns few or no rows — that is the finding, not an error.
"""

from __future__ import annotations

import re

from .flatten import flatten_records
from .source import RegistrySource

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "from",
        "by", "is", "are", "be", "that", "this", "it", "as", "at", "into", "when",
        "need", "needs", "want", "automatically", "auto", "create", "created",
    }
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in _STOPWORDS}


def registry_search(
    source: RegistrySource,
    query: str,
    systems_filter: list[str] | None = None,
) -> list[dict]:
    """Return flattened capability matches ranked by token overlap (may be empty)."""
    rows = flatten_records(source.records())
    q_tokens = _tokens(query)
    for s in systems_filter or []:
        q_tokens |= _tokens(s)
    if not q_tokens:
        return []

    scored: list[tuple[int, dict]] = []
    for row in rows:
        haystack = " ".join(
            [row["capability_statement"], row["record_name"], row["category"]]
        )
        overlap = len(q_tokens & _tokens(haystack))
        if overlap > 0:
            scored.append((overlap, row))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["record_id"], pair[1]["capability_id"]))
    return [row for _, row in scored]
