"""The sensitivity overlay (orchestrator-contract §6, context §6).

`unspecified` is treated as sensitive-until-confirmed — functionally equivalent
to `customer` for routing decisions. The overlay raises guardrails; it NEVER
changes the route. It must not silently downgrade to `none` anywhere.
"""

from __future__ import annotations

from .enums import DataSensitivity, Weight

# Sensitivity levels that force redaction in logs and the security review.
_SENSITIVE = frozenset(
    {
        DataSensitivity.CUSTOMER,
        DataSensitivity.FINANCIAL,
        DataSensitivity.REGULATED,
        DataSensitivity.UNSPECIFIED,
    }
)


def effective_sensitivity(value: DataSensitivity) -> DataSensitivity:
    """Resolve the routing-effective sensitivity.

    `unspecified` is treated as `customer` for routing decisions; every other
    value passes through unchanged. Never returns `none` for `unspecified`.
    """
    if value is DataSensitivity.UNSPECIFIED:
        return DataSensitivity.CUSTOMER
    return value


def is_sensitive(value: DataSensitivity) -> bool:
    """True for customer/financial/regulated/unspecified — drives redaction."""
    return value in _SENSITIVE


def forces_security_review(value: DataSensitivity, *, is_build: bool) -> bool:
    """Any build carries the (two-agent) security review; sensitive data guarantees it.

    Security review is non-bypassable on builds regardless of sensitivity; this
    helper exists so callers can assert the overlay never *suppresses* it.
    """
    return is_build


def forces_rnd_signoff(value: DataSensitivity, weight: Weight) -> bool:
    """R&D security sign-off fires on heavy work, or on sensitive work.

    `heavy + unspecified` is treated as `heavy + sensitive` (§6).
    """
    return weight is Weight.HEAVY or is_sensitive(value)
