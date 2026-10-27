"""Segmentation unit tests: normalization + deterministic requirement splitting.

Pure-function tests (no DB): every strategy, heading/section handling,
continuation rules, offsets/lines, confidence values, and determinism —
including the span invariant (`normalized[start:end] == text`) and
re-segmentation stability (stored `source_text` reproduces identical rows).
"""

from app.services.segmentation import (
    MAX_REQUIREMENTS,
    normalize_text,
    segment_requirements,
)


def _segments(text: str):  # segment() always runs on normalized input
    return segment_requirements(normalize_text(text))


# --- normalization ----------------------------------------------------------


def test_normalize_unifies_line_endings() -> None:
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_normalize_strips_trailing_whitespace_only() -> None:
    assert normalize_text("keep  inner   \n  indented\t\n") == "keep  inner\n  indented"


def test_normalize_collapses_blank_runs_and_edges() -> None:
    assert normalize_text("\n\n\na\n\n\n\n\nb\n\n") == "a\n\n\nb"


def test_normalize_removes_bom_and_zero_width_chars() -> None:
    assert normalize_text("\ufeffa\u200bb\u200cc\u200dd\ufeffe") == "abcde"


def test_normalize_preserves_unicode_and_case() -> None:
    text = " authenticate Naïve café 中文 ß SHALL "
    assert normalize_text(text) == " authenticate Naïve café 中文 ß SHALL"


def test_normalize_blank_to_empty() -> None:
    assert normalize_text("") == ""
    assert normalize_text("   \n\t\n  ") == ""
    assert normalize_text("\r\n") == ""


# --- requirement-ID strategy ------------------------------------------------


def test_requirement_id_variants() -> None:
    segments = _segments(
        "FR-001: The system shall allow login.\n"
        "REQ002 The admin must approve accounts.\n"
        "NFR-12 - The dashboard shall load fast.\n"
        "fr-3. The API should return JSON.\n"
    )
    assert [(s.identifier, s.strategy, s.confidence) for s in segments] == [
        ("FR-001", "requirement_id", 0.95),
        ("REQ002", "requirement_id", 0.95),
        ("NFR-12", "requirement_id", 0.95),
        ("fr-3", "requirement_id", 0.95),  # stored verbatim, trailing dot cut
    ]
    assert segments[0].text == "The system shall allow login."


def test_requirement_id_needs_no_modal_signal() -> None:
    (segment,) = _segments("BR-7 Background context for the release.\n")
    assert (segment.identifier, segment.confidence) == ("BR-7", 0.95)


def test_bare_id_consumes_body_below() -> None:
    (segment,) = _segments("NFR-01\nThe dashboard shall load in 2 seconds.\n")
    assert segment.identifier == "NFR-01"
    assert segment.text == "The dashboard shall load in 2 seconds."


def test_bare_id_without_body_is_skipped() -> None:
    assert _segments("FR-001\n\nFR-002\n") == []


# --- decimal / numbered strategies ------------------------------------------


def test_decimal_with_signal_is_requirement() -> None:
    (segment,) = _segments("3.2.1 The system shall support export.\n")
    assert (segment.identifier, segment.strategy, segment.confidence) == ("3.2.1", "decimal", 0.90)


def test_decimal_without_signal_is_heading() -> None:
    segments = _segments("3.2 Scope\n\nThe system shall log out users.\n")
    assert len(segments) == 1
    assert segments[0].section == "Scope"
    assert segments[0].strategy == "paragraph"  # the heading itself is not a req


def test_decimal_heading_nesting_by_depth() -> None:
    segments = _segments("3 Functional\n3.1 Auth\n3.1.2 Login\n- The system shall use MFA.\n")
    assert segments[0].section == "Functional > Auth > Login"


def test_numbered_with_signal_is_requirement() -> None:
    (segment,) = _segments("1. The admin must approve new accounts.\n")
    assert (segment.identifier, segment.strategy, segment.confidence) == ("1", "numbered", 0.90)


def test_numbered_short_line_without_signal_is_heading() -> None:
    segments = _segments("1. Introduction\n\nThe system shall start fast.\n")
    assert [s.text for s in segments] == ["The system shall start fast."]
    assert segments[0].section == "Introduction"


def test_numbered_long_line_without_signal_is_requirement() -> None:
    (segment,) = _segments(
        "2. Additional background information about the legacy integration landscape.\n"
    )
    assert (segment.strategy, segment.confidence) == ("numbered", 0.60)


def test_numbered_paren_style() -> None:
    (segment,) = _segments("4) The cache should expire hourly.\n")
    assert (segment.identifier, segment.strategy) == ("4", "numbered")


def test_marker_echo_rest_stays_exact() -> None:
    # Rest text repeating the marker number must NOT resolve to the marker's
    # own offset (offsets are measured from the regex match, not str.index).
    (segment,) = _segments("12. 12 users shall log in daily\n")
    assert segment.text == "12 users shall log in daily"
    assert segment.start_offset == 4


def test_weak_signal_modulates_marker_confidence() -> None:
    (segment,) = _segments("5. The report will refresh nightly.\n")
    assert (segment.strategy, segment.confidence) == ("numbered", 0.75)


# --- bullet strategy --------------------------------------------------------


def test_bullet_styles() -> None:
    segments = _segments(
        "- The system shall retry sends.\n"
        "* The queue must persist jobs.\n"
        "+ The cache should warm up.\n"
        "• The log shall rotate daily.\n"
        "(a) The alert must page on-call.\n"
    )
    assert [s.strategy for s in segments] == ["bullet"] * 5
    assert [s.identifier for s in segments] == [None] * 5
    assert segments[0].text == "The system shall retry sends."
    assert segments[0].confidence == 0.80


def test_bullet_without_signal_gets_lowest_marker_confidence() -> None:
    (segment,) = _segments("- Legacy import notes.\n")
    assert (segment.strategy, segment.confidence) == ("bullet", 0.50)


def test_markdown_bold_is_not_a_bullet() -> None:
    assert _segments("**Bold statement**\n") == []


# --- headings / sections ----------------------------------------------------


def test_hash_headings_build_section_path() -> None:
    segments = _segments(
        "# Requirements\n## Auth\n- The system shall use MFA.\n"
        "## Billing\n- Invoices must be PDFs.\n"
    )
    assert [s.section for s in segments] == ["Requirements > Auth", "Requirements > Billing"]


def test_caps_heading_becomes_section() -> None:
    segments = _segments("ACCEPTANCE CRITERIA\n\n- The build must pass.\n")
    assert segments[0].section == "ACCEPTANCE CRITERIA"


def test_shouted_requirement_is_not_a_heading() -> None:
    (segment,) = _segments("THE SYSTEM SHALL LOG EVERYTHING\n")
    assert segment.strategy == "paragraph"
    assert segment.confidence == 0.55


def test_no_heading_means_no_section() -> None:
    (segment,) = _segments("The system shall boot.\n")
    assert segment.section is None


def test_dotless_numbered_heading_becomes_section() -> None:
    segments = _segments("3 Functional Requirements\n\n- The system shall scale.\n")
    assert segments[0].section == "Functional Requirements"


def test_dotless_line_with_signal_is_requirement_not_heading() -> None:
    (segment,) = _segments("3 The system shall provide audit logs\n")
    assert segment.strategy == "paragraph"
    assert segment.section is None


def test_dotless_line_starting_lowercase_is_skipped() -> None:
    assert _segments("5 failures occurred last quarter\n") == []


def test_section_path_truncates_at_200_chars() -> None:
    long_title = "S" * 150
    segments = _segments(f"# {long_title}\n## {long_title}\n- The system shall fit.\n")
    assert segments[0].section is not None
    assert len(segments[0].section) == 200


# --- paragraph strategy -----------------------------------------------------


def test_paragraph_needs_strong_signal() -> None:
    (segment,) = _segments("Our users are required to verify email before posting.\n")
    assert (segment.strategy, segment.confidence) == ("paragraph", 0.55)


def test_paragraph_weak_signal_only_is_skipped() -> None:
    assert _segments("The system will be updated quarterly.\n") == []
    assert _segments("This document describes the platform.\n") == []


def test_paragraph_imperative_accepted_at_lowest_confidence() -> None:
    (segment,) = _segments("Display an error message on failure.\n")
    assert (segment.strategy, segment.confidence) == ("paragraph", 0.50)


def test_multiline_paragraph_is_one_requirement() -> None:
    (segment,) = _segments(
        "The system shall allow login. It must lock after 5 failures.\nSecond sentence here.\n"
    )
    assert segment.strategy == "paragraph"
    assert "\n" in segment.text  # internal breaks preserved, never reflowed


# --- continuation rules -----------------------------------------------------


def test_indented_line_continues_requirement() -> None:
    (segment,) = _segments("1. The system shall export.\n   CSV and JSON formats.\n")
    assert segment.text == "The system shall export.\n   CSV and JSON formats."


def test_unterminated_sentence_continues_unindented() -> None:
    (segment,) = _segments("1. The system shall support\nCSV import.\n")
    assert segment.text == "The system shall support\nCSV import."


def test_terminated_sentence_breaks_before_unindented_prose() -> None:
    segments = _segments("1. The system shall export.\nIt must also import.\n")
    assert [s.text for s in segments] == ["The system shall export.", "It must also import."]
    assert segments[1].strategy == "paragraph"


def test_marker_and_blank_lines_terminate() -> None:
    segments = _segments("1. The system shall export\nCSV too.\n2. The system shall import.\n")
    assert [s.text for s in segments] == [
        "The system shall export\nCSV too.",
        "The system shall import.",
    ]


def test_colon_does_not_terminate() -> None:
    (segment,) = _segments("1. The system shall do the following:\nEncrypt data at rest.\n")
    assert segment.text == "The system shall do the following:\nEncrypt data at rest."


# --- offsets / lines / determinism ------------------------------------------


def test_offsets_and_lines_are_exact() -> None:
    normalized = normalize_text("Intro line.\n\nFR-9: The system shall persist.\nTail.\n")
    (segment,) = segment_requirements(normalized)
    assert segment.text == "The system shall persist."
    assert normalized[segment.start_offset : segment.end_offset] == segment.text
    assert (segment.line_start, segment.line_end) == (3, 3)


def test_multiline_span_covers_exact_lines() -> None:
    normalized = normalize_text("1. The system shall support\nCSV import.\n")
    (segment,) = segment_requirements(normalized)
    assert (segment.line_start, segment.line_end) == (1, 2)
    assert normalized[segment.start_offset : segment.end_offset] == segment.text


def test_span_invariant_holds_on_complex_document() -> None:
    normalized = normalize_text(
        "# SRS\n\nFR-001: The system shall boot.\nWrapped tail\n\n"
        "3.1 Scope\n\n- The cache should warm.\n\nPlain prose without verbs here.\n\n"
        "NFR-2\nLatency must stay low.\n"
    )
    segments = segment_requirements(normalized)
    # "Wrapped tail" (unindented after a terminated sentence, no signal) and the
    # signal-less prose line are skipped; everything else is kept in doc order.
    assert len(segments) == 3
    for segment in segments:
        assert normalized[segment.start_offset : segment.end_offset] == segment.text
    # document order, positions implied by order
    assert [s.strategy for s in segments] == ["requirement_id", "bullet", "requirement_id"]
    assert segments[1].section == "SRS > Scope"  # hash + decimal headings nest


def test_determinism_same_input_same_segments() -> None:
    text = normalize_text("FR-1: The system shall a.\n\n- The b must c.\n\nScope\n")
    first = segment_requirements(text)
    second = segment_requirements(text)
    assert first == second
    # re-segmentation of the stored text reproduces identical segments
    assert segment_requirements(normalize_text(text)) == first


def test_empty_input_yields_no_segments() -> None:
    assert segment_requirements("") == []
    assert segment_requirements(normalize_text("  \n ")) == []


def test_max_requirements_cap_is_documented_constant() -> None:
    assert MAX_REQUIREMENTS == 2000
