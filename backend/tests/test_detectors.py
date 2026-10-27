"""Detector unit tests: each of the 11 detectors, isolated.

Every detector is tested through its own function (positive + negative +
guard cases) — never through the full engine, so a failure names the exact
detector. Cross-detector behavior (dedup, scoring) lives in test_scoring.py.
"""

from app.analysis.detectors import (
    REGISTRY,
    Finding,
    detect_absolute_language,
    detect_ambiguous_operator,
    detect_incomplete_requirement,
    detect_missing_constraint,
    detect_missing_measurable,
    detect_optional_language,
    detect_passive_actor,
    detect_pronoun_reference,
    detect_subjective_term,
    detect_undefined_terminology,
    detect_vague_quantifier,
)


def _summaries(text: str, findings: list[Finding]) -> list[tuple[str, str, str]]:
    for finding in findings:  # every finding slices its phrase verbatim
        assert text[finding.start_offset : finding.end_offset] == finding.phrase
        assert finding.start_offset < finding.end_offset
    return [(f.detector_id, f.severity, f.phrase) for f in findings]


def test_registry_has_eleven_unique_detectors() -> None:
    assert len(REGISTRY) == 11
    ids = [detector[0] for detector, _ in REGISTRY]
    assert len(set(ids)) == 11
    assert all("-" in detector_id for detector_id in ids)  # kebab-case ids


# ---------------------------------------------------------------------------
# vague-quantifier
# ---------------------------------------------------------------------------


def test_vague_quantifier_flags_bare_quantities() -> None:
    text = "The system shall support several payment methods."
    assert _summaries(text, detect_vague_quantifier(text)) == [
        ("vague-quantifier", "medium", "several")
    ]
    multi = "The report shall cover a number of regions."
    assert _summaries(multi, detect_vague_quantifier(multi)) == [
        ("vague-quantifier", "medium", "a number of")
    ]


def test_vague_quantifier_skips_bounded_frame_and_substrings() -> None:
    assert detect_vague_quantifier("Support as many as 5 methods.") == []
    assert detect_vague_quantifier("Notify someone on failure.") == []  # not "some"
    assert detect_vague_quantifier("The system shall support 5 methods.") == []


# ---------------------------------------------------------------------------
# subjective-term
# ---------------------------------------------------------------------------


def test_subjective_term_flags_quality_words() -> None:
    text = "The application should provide a fast response."
    assert _summaries(text, detect_subjective_term(text)) == [("subjective-term", "medium", "fast")]
    hyphen = "The UI shall be user-friendly."
    assert _summaries(hyphen, detect_subjective_term(hyphen)) == [
        ("subjective-term", "medium", "user-friendly")
    ]
    phrase = "The server shall deliver high performance."
    assert _summaries(phrase, detect_subjective_term(phrase)) == [
        ("subjective-term", "medium", "high performance")
    ]


def test_subjective_term_skips_externally_defined_terms() -> None:
    text = "The UI shall be user-friendly as defined in the style guide."
    assert detect_subjective_term(text) == []
    assert detect_subjective_term("Respond within 2 seconds.") == []


# ---------------------------------------------------------------------------
# missing-measurable-criteria
# ---------------------------------------------------------------------------


def test_missing_measurable_flags_claim_span() -> None:
    text = "The system should respond quickly."
    assert _summaries(text, detect_missing_measurable(text)) == [
        ("missing-measurable-criteria", "high", "respond quickly")
    ]
    text2 = "The application must be highly available."
    assert _summaries(text2, detect_missing_measurable(text2)) == [
        ("missing-measurable-criteria", "high", "highly available")
    ]


def test_missing_measurable_skips_thresholded_claims() -> None:
    assert detect_missing_measurable("Respond within 2 seconds.") == []
    assert detect_missing_measurable("Respond within two seconds.") == []
    assert detect_missing_measurable("The system shall provide 99.9% uptime.") == []
    assert detect_missing_measurable("Support 1000 concurrent users.") == []


# ---------------------------------------------------------------------------
# optional-language
# ---------------------------------------------------------------------------


def test_optional_language_flags_modals_and_hedges() -> None:
    for term in ("may", "might", "could", "should", "possibly"):
        text = f"The system {term} retry failed uploads."
        (finding,) = detect_optional_language(text)
        assert (finding.detector_id, finding.severity) == ("optional-language", "low")
    hedge = "Retry when necessary."
    assert _summaries(hedge, detect_optional_language(hedge)) == [
        ("optional-language", "low", "when necessary")
    ]


def test_optional_language_guards_and_commitment_words() -> None:
    assert detect_optional_language("Release scheduled for May 2026.") == []
    assert detect_optional_language("The system could not start.") == []
    assert detect_optional_language("The system shall start.") == []
    assert detect_optional_language("The system must start.") == []
    assert detect_optional_language("Users can export data.") == []  # permission


# ---------------------------------------------------------------------------
# pronoun-reference
# ---------------------------------------------------------------------------


def test_pronoun_reference_flags_ambiguous_it() -> None:
    text = "The server sends the request to the client and it stores the result."
    assert _summaries(text, detect_pronoun_reference(text)) == [
        ("pronoun-reference", "medium", "it")
    ]


def test_pronoun_reference_accepts_single_human_they() -> None:
    text = "The user logs in. They receive a verification email."
    assert detect_pronoun_reference(text) == []
    ambiguous = "The server sends requests to clients. They store them."
    assert {f.phrase for f in detect_pronoun_reference(ambiguous)} == {"They", "them"}


def test_pronoun_reference_bare_vs_modifying_demonstratives() -> None:
    bare = "This is required for compliance."
    assert _summaries(bare, detect_pronoun_reference(bare)) == [
        ("pronoun-reference", "low", "This")
    ]
    assert detect_pronoun_reference("This report shows the totals.") == []
    assert detect_pronoun_reference("The IT department approves access.") == []
    assert detect_pronoun_reference("The system restarts when it fails.") == []


# ---------------------------------------------------------------------------
# ambiguous-operator
# ---------------------------------------------------------------------------


def test_ambiguous_operator_flags_open_endings() -> None:
    text = "The system shall support email and/or SMS notifications."
    assert _summaries(text, detect_ambiguous_operator(text)) == [
        ("ambiguous-operator", "high", "and/or")
    ]
    etc = "Select a plan, a region, etc."
    assert _summaries(etc, detect_ambiguous_operator(etc)) == [
        ("ambiguous-operator", "high", "etc.")
    ]
    bore = "The system shall support email, SMS, or push notifications."
    assert _summaries(bore, detect_ambiguous_operator(bore)) == [
        ("ambiguous-operator", "low", "or")
    ]
    mixed = "The system shall log errors and warnings or alerts."
    assert _summaries(mixed, detect_ambiguous_operator(mixed)) == [
        ("ambiguous-operator", "low", "or")
    ]


def test_ambiguous_operator_skips_plain_and_explicit_or() -> None:
    assert detect_ambiguous_operator("Enter your username or email.") == []
    assert detect_ambiguous_operator("Use either email or SMS.") == []
    assert detect_ambiguous_operator("Choose whether email or SMS.") == []


# ---------------------------------------------------------------------------
# undefined-terminology
# ---------------------------------------------------------------------------


def test_undefined_terminology_flags_attached_qualifiers() -> None:
    text = "The system shall use standard security."
    assert _summaries(text, detect_undefined_terminology(text)) == [
        ("undefined-terminology", "low", "standard")
    ]
    rules = "Apply the business rules."
    assert _summaries(rules, detect_undefined_terminology(rules)) == [
        ("undefined-terminology", "low", "business")
    ]


def test_undefined_terminology_skips_bare_and_framed_uses() -> None:
    assert detect_undefined_terminology("Comply with the standard.") == []
    assert detect_undefined_terminology("Follow the industry standard.") == []
    assert detect_undefined_terminology("Use standard-compliant storage.") == []


# ---------------------------------------------------------------------------
# absolute-language
# ---------------------------------------------------------------------------


def test_absolute_language_flags_absolutes() -> None:
    text = "The system must always be available."
    assert _summaries(text, detect_absolute_language(text)) == [
        ("absolute-language", "medium", "always")
    ]
    weak = "The system shall accept any file format."
    assert _summaries(weak, detect_absolute_language(weak)) == [("absolute-language", "low", "any")]
    circumstance = "Retry under all circumstances."
    assert _summaries(circumstance, detect_absolute_language(circumstance)) == [
        ("absolute-language", "medium", "under all circumstances")
    ]


def test_absolute_language_skips_bounded_and_scheduled_uses() -> None:
    assert detect_absolute_language("Support any of the following: A, B.") == []
    assert detect_absolute_language("Back up data every day.") == []
    assert detect_absolute_language("Support instant messaging.") == []


# ---------------------------------------------------------------------------
# passive-actor
# ---------------------------------------------------------------------------


def test_passive_actor_flags_actorless_passives() -> None:
    text = "The account shall be created after registration."
    assert _summaries(text, detect_passive_actor(text)) == [
        ("passive-actor", "medium", "be created")
    ]
    irregular = "The report shall be written nightly."
    assert _summaries(irregular, detect_passive_actor(irregular)) == [
        ("passive-actor", "medium", "be written")
    ]
    adverb = "The file shall be automatically deleted."
    assert _summaries(adverb, detect_passive_actor(adverb)) == [
        ("passive-actor", "medium", "be automatically deleted")
    ]


def test_passive_actor_skips_explicit_actors_and_states() -> None:
    assert detect_passive_actor("The account shall be created by the server.") == []
    assert detect_passive_actor("A password is required.") == []
    assert detect_passive_actor("The system shall create the account.") == []


# ---------------------------------------------------------------------------
# missing-constraint
# ---------------------------------------------------------------------------


def test_missing_constraint_flags_bare_actions() -> None:
    text = "The system shall process requests."
    assert _summaries(text, detect_missing_constraint(text)) == [
        ("missing-constraint", "high", "process requests")
    ]
    perm = "Users can modify records."
    (finding,) = detect_missing_constraint(perm)
    assert (finding.detector_id, finding.severity, finding.phrase) == (
        "missing-constraint",
        "high",
        "modify records",
    )
    assert "permission" in finding.reason  # can/may names the permission facet


def test_missing_constraint_skips_detailed_requirements() -> None:
    assert detect_missing_constraint("Process requests within 2 seconds.") == []
    assert detect_missing_constraint("The system shall log out idle users.") == []
    assert detect_missing_constraint("Support authentication.") == []


# ---------------------------------------------------------------------------
# incomplete-requirement
# ---------------------------------------------------------------------------


def test_incomplete_requirement_flags_dangling_modals() -> None:
    text = "The system shall..."
    assert _summaries(text, detect_incomplete_requirement(text)) == [
        ("incomplete-requirement", "critical", "shall...")
    ]
    bare = "Users must"
    assert _summaries(bare, detect_incomplete_requirement(bare)) == [
        ("incomplete-requirement", "critical", "must")
    ]


def test_incomplete_requirement_flags_placeholders_case_sensitively() -> None:
    text = "The API rate limit is TBD."
    assert _summaries(text, detect_incomplete_requirement(text)) == [
        ("incomplete-requirement", "critical", "TBD")
    ]
    assert detect_incomplete_requirement("Show the todo list.") == []


def test_incomplete_requirement_flags_fragments() -> None:
    trailing = "Support authentication for..."
    assert _summaries(trailing, detect_incomplete_requirement(trailing)) == [
        ("incomplete-requirement", "high", "for...")
    ]
    fragment = "Authentication system."
    assert _summaries(fragment, detect_incomplete_requirement(fragment)) == [
        ("incomplete-requirement", "high", "Authentication system.")
    ]


def test_incomplete_requirement_skips_complete_shorts() -> None:
    assert detect_incomplete_requirement("Support authentication.") == []
    assert detect_incomplete_requirement("Password minimum length: 12.") == []
    assert detect_incomplete_requirement("The system shall allow login.") == []
