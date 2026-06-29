from app.enums import DataSensitivity, Weight
from app.sensitivity import (
    effective_sensitivity,
    forces_rnd_signoff,
    forces_security_review,
    is_sensitive,
)


def test_unspecified_is_customer_equivalent_for_routing():
    assert effective_sensitivity(DataSensitivity.UNSPECIFIED) is DataSensitivity.CUSTOMER


def test_unspecified_never_downgrades_to_none():
    assert effective_sensitivity(DataSensitivity.UNSPECIFIED) is not DataSensitivity.NONE


def test_passthrough_for_explicit_values():
    for v in (DataSensitivity.NONE, DataSensitivity.INTERNAL, DataSensitivity.REGULATED):
        assert effective_sensitivity(v) is v


def test_is_sensitive_set():
    assert is_sensitive(DataSensitivity.UNSPECIFIED)
    assert is_sensitive(DataSensitivity.CUSTOMER)
    assert is_sensitive(DataSensitivity.FINANCIAL)
    assert is_sensitive(DataSensitivity.REGULATED)
    assert not is_sensitive(DataSensitivity.INTERNAL)
    assert not is_sensitive(DataSensitivity.NONE)


def test_security_review_forced_on_any_build():
    assert forces_security_review(DataSensitivity.NONE, is_build=True)
    assert not forces_security_review(DataSensitivity.NONE, is_build=False)


def test_rnd_signoff_on_heavy_or_sensitive():
    # heavy regardless of sensitivity
    assert forces_rnd_signoff(DataSensitivity.NONE, Weight.HEAVY)
    # light but sensitive (unspecified treated as sensitive)
    assert forces_rnd_signoff(DataSensitivity.UNSPECIFIED, Weight.LIGHT)
    # light + non-sensitive: no R&D sign-off
    assert not forces_rnd_signoff(DataSensitivity.INTERNAL, Weight.LIGHT)
