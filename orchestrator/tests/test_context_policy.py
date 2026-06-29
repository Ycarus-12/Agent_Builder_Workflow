from app.context_policy import ContextItem, context_for, is_judgment_stage


def test_extraction_is_mechanical_extract_only():
    items = context_for("intake_extract")
    assert items == frozenset({ContextItem.STRUCTURED_EXTRACT})
    assert is_judgment_stage("intake_extract") is False


def test_triage_is_judgment_gets_transcript():
    items = context_for("triage")
    assert ContextItem.RAW_TRANSCRIPT in items
    assert ContextItem.STRUCTURED_EXTRACT in items
    assert ContextItem.STACK_CHECK_FINDING in items
    assert is_judgment_stage("triage") is True


def test_rom_gets_option_list_not_transcript_or_finding():
    items = context_for("cost_rom")
    assert items == frozenset(
        {ContextItem.STRUCTURED_EXTRACT, ContextItem.TRIAGE_OPTION_LIST}
    )
    assert ContextItem.RAW_TRANSCRIPT not in items
    assert ContextItem.STACK_CHECK_FINDING not in items


def test_deepdive_gets_full_context():
    items = context_for("cost_deepdive")
    assert items == frozenset(
        {
            ContextItem.STRUCTURED_EXTRACT,
            ContextItem.RAW_TRANSCRIPT,
            ContextItem.STACK_CHECK_FINDING,
            ContextItem.ROM_OUTPUT,
            ContextItem.SELECTED_OPTIONS,
        }
    )


def test_re_triage_adds_director_notes():
    base = context_for("triage")
    re = context_for("triage", re_triage=True)
    assert ContextItem.DIRECTOR_NOTES not in base
    assert ContextItem.DIRECTOR_NOTES in re


def test_unknown_stage_defaults_mechanical():
    assert context_for("some_future_stage") == frozenset({ContextItem.STRUCTURED_EXTRACT})
