from app.markers import MarkerMisuse, detect_signoff, strip_marker_line


def test_valid_marker_on_final_line():
    resp = "Great, I've captured everything.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]"
    result = detect_signoff(resp)
    assert result.fired is True
    assert result.is_misuse is False


def test_marker_not_on_final_line_is_misuse():
    resp = "[[INTAKE_SIGNOFF_CONFIRMED]]\nWait, one more thing."
    result = detect_signoff(resp)
    assert result.fired is False
    assert result.misuse is MarkerMisuse.NOT_FINAL_LINE


def test_multiple_markers_is_misuse():
    resp = "[[INTAKE_SIGNOFF_CONFIRMED]]\nthanks\n[[INTAKE_SIGNOFF_CONFIRMED]]"
    result = detect_signoff(resp)
    assert result.fired is False
    assert result.misuse is MarkerMisuse.MULTIPLE_OCCURRENCES


def test_marker_not_alone_on_line_is_misuse():
    resp = "All set [[INTAKE_SIGNOFF_CONFIRMED]]"
    result = detect_signoff(resp)
    assert result.fired is False
    assert result.misuse is MarkerMisuse.NOT_ALONE_ON_LINE


def test_no_marker():
    assert detect_signoff("just a normal turn").fired is False


def test_strip_marker_line():
    resp = "Thanks, that's everything I need.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]"
    assert strip_marker_line(resp) == "Thanks, that's everything I need."
