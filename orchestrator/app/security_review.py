"""Deterministic reconciliation of the two security agents (context §6, §9.3).

The vulnerabilities and governance agents run BLIND (neither sees the other); the
orchestrator reconciles their findings and derives the block — the agents never
emit a verdict. Security is non-bypassable, including by the Director: a Critical
finding blocks and escalates; a material disagreement routes to the Director.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import DataSensitivity, Weight
from .sensitivity import forces_rnd_signoff

# Severity ordering (highest first); blocking threshold is Critical.
_SEVERITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Informational": 0}


def _max_rank(findings: list[dict]) -> int:
    return max((_SEVERITY_RANK.get(f.get("severity", "Informational"), 0) for f in findings), default=0)


@dataclass(frozen=True)
class SecurityOutcome:
    blocked: bool            # a Critical finding — must remediate, non-bypassable
    critical: bool           # at least one Critical finding (either agent)
    to_director: bool        # a High finding or a material disagreement to adjudicate
    disagreement: bool       # the two agents diverge materially
    rnd_signoff_required: bool

    @property
    def clears_to_gate_2(self) -> bool:
        """True only when nothing blocks and no Director adjudication is pending."""
        return not self.blocked and not self.to_director


def reconcile_security(
    vuln_findings: list[dict],
    gov_findings: list[dict],
    *,
    weight: Weight,
    data_sensitivity: DataSensitivity,
) -> SecurityOutcome:
    """Combine the two agents' findings into a single deterministic outcome."""
    v_rank, g_rank = _max_rank(vuln_findings), _max_rank(gov_findings)
    top = max(v_rank, g_rank)
    critical = top >= _SEVERITY_RANK["Critical"]
    high = top >= _SEVERITY_RANK["High"]

    # Material disagreement heuristic (audited): one agent raises a High+ concern while
    # the other returns nothing at all — the orchestrator routes that to the Director.
    disagreement = (
        (v_rank >= _SEVERITY_RANK["High"] and not gov_findings)
        or (g_rank >= _SEVERITY_RANK["High"] and not vuln_findings)
    )

    return SecurityOutcome(
        blocked=critical,
        critical=critical,
        to_director=high or disagreement,
        disagreement=disagreement,
        rnd_signoff_required=forces_rnd_signoff(data_sensitivity, weight),
    )
