"""Engine tests: dedup, transparent scoring, bands, health, determinism.

Detector accuracy lives in test_detectors.py; this suite pins the engine
contract (the project contract): the deduction table, clamping, the mean,
bands, severity derivation, health partitioning, and byte-identical
repeat runs.
"""

from app.analysis.detectors import REGISTRY, Finding
from app.analysis.engine import (
    DEDUCTIONS,
    HEALTH_DIMENSIONS,
    analyze_requirement,
    band_for_score,
    deduplicate,
    health_for_findings,
    overall_score,
    score_findings,
    severity_counts,
    severity_of,
)


def _finding(
    detector_id: str = "subjective-term",
    severity: str = "medium",
    start: int = 0,
    end: int = 4,
) -> Finding:
    assert severity in DEDUCTIONS
    return Finding(
        detector_id=detector_id,
        category="Test",
        severity=severity,  # type: ignore[arg-type]
        phrase="test",
        start_offset=start,
        end_offset=end,
        reason="reason",
        recommendation="recommendation",
    )


# ---------------------------------------------------------------------------
# Deduction table + clamping (PROJECT_SPEC §6: low −5, medium −10, high −15,
# critical −20; clamp 0–100)
# ---------------------------------------------------------------------------


def test_deduction_table_matches_spec() -> None:
    assert DEDUCTIONS == {"low": 5, "medium": 10, "high": 15, "critical": 20}


def test_score_findings_single_severities() -> None:
    assert score_findings([]) == 100
    assert score_findings([_finding(severity="low")]) == 95
    assert score_findings([_finding(severity="medium")]) == 90
    assert score_findings([_finding(severity="high")]) == 85
    assert score_findings([_finding(severity="critical")]) == 80


def test_score_findings_combinations_and_clamp() -> None:
    combo = [_finding(severity=s) for s in ("low", "medium", "high", "critical")]
    assert score_findings(combo) == 50  # 100 − 5 − 10 − 15 − 20
    assert score_findings([_finding(severity="critical")] * 6) == 0  # clamped
    assert score_findings([_finding(severity="low")] * 100) == 0  # clamped


def test_severity_of_derives_highest_or_none() -> None:
    assert severity_of([]) is None
    assert severity_of([_finding(severity="low"), _finding(severity="high")]) == "high"


# ---------------------------------------------------------------------------
# Dedup: exact dupes collapse; identical spans keep highest severity
# (registry-order tie-break); distinct overlaps survive
# ---------------------------------------------------------------------------


def test_deduplicate_collapses_exact_duplicates() -> None:
    dupes = [_finding("vague-quantifier", "medium", 0, 7)] * 3
    assert deduplicate(dupes) == dupes[:1]


def test_deduplicate_identical_span_keeps_highest_severity() -> None:
    low = _finding("optional-language", "low", 5, 9)
    high = _finding("missing-constraint", "high", 5, 9)
    assert deduplicate([low, high]) == [high]
    assert deduplicate([high, low]) == [high]  # input order irrelevant


def test_deduplicate_tie_breaks_by_registry_order() -> None:
    order = [detector[0] for detector, _ in REGISTRY]
    first, second = order[0], order[-1]
    assert deduplicate([_finding(second, "medium", 0, 3), _finding(first, "medium", 0, 3)]) == [
        _finding(first, "medium", 0, 3)
    ]


def test_deduplicate_keeps_distinct_overlapping_spans() -> None:
    word = _finding("subjective-term", "medium", 19, 26)  # "quickly"
    claim = _finding("missing-measurable-criteria", "high", 11, 26)
    assert deduplicate([word, claim]) == [claim, word]  # span-sorted, both kept


# ---------------------------------------------------------------------------
# Overall score: arithmetic mean, half-up; bands per spec
# ---------------------------------------------------------------------------


def test_overall_score_is_half_up_mean() -> None:
    assert overall_score([100, 85]) == 93  # 92.5 rounds UP, never banker's 92
    assert overall_score([100, 100, 85]) == 95
    assert overall_score([100]) == 100
    assert overall_score([]) == 100


def test_band_for_score_boundaries() -> None:
    assert [(s, band_for_score(s)) for s in (100, 80)] == [(100, "low"), (80, "low")]
    assert band_for_score(79) == band_for_score(60) == "moderate"
    assert band_for_score(59) == band_for_score(40) == "high"
    assert band_for_score(39) == band_for_score(0) == "very_high"


# ---------------------------------------------------------------------------
# Health: every detector in exactly one dimension; values traceable
# ---------------------------------------------------------------------------


def test_health_partitions_every_detector() -> None:
    registry_ids = {detector[0] for detector, _ in REGISTRY}
    mapped = [d for ids in HEALTH_DIMENSIONS.values() for d in ids]
    assert sorted(mapped) == sorted(registry_ids)  # each exactly once
    assert set(HEALTH_DIMENSIONS) == {
        "clarity",
        "specificity",
        "measurability",
        "completeness",
    }


def test_health_for_findings_subtracts_mapped_deductions() -> None:
    findings = [
        _finding("subjective-term", "medium"),  # measurability −10
        _finding("missing-measurable-criteria", "high"),  # measurability −15
        _finding("vague-quantifier", "medium"),  # specificity −10
    ]
    assert health_for_findings(findings) == {
        "measurability": 75,
        "specificity": 90,
        "clarity": 100,
        "completeness": 100,
    }
    criticals = [_finding("incomplete-requirement", "critical")] * 10
    assert health_for_findings(criticals)["completeness"] == 0  # clamped


def test_severity_counts_totals() -> None:
    findings = [_finding(severity=s) for s in ("low", "low", "high")]
    assert severity_counts(findings) == {"low": 2, "medium": 0, "high": 1, "critical": 0}
    assert severity_counts([]) == {"low": 0, "medium": 0, "high": 0, "critical": 0}


# ---------------------------------------------------------------------------
# Brief §43 acceptance examples
# ---------------------------------------------------------------------------


def test_brief_example_positive_pair() -> None:
    analysis = analyze_requirement("The system should respond quickly.")
    ids = {f.detector_id for f in analysis.findings}
    assert {"subjective-term", "missing-measurable-criteria"} <= ids
    assert ids == {
        "optional-language",
        "missing-measurable-criteria",
        "subjective-term",
    }
    assert analysis.score == 70  # 100 − 5 − 15 − 10
    assert analysis.severity == "high"


def test_brief_example_thresholded_negative() -> None:
    analysis = analyze_requirement("The system shall respond within 2 seconds.")
    assert analysis.findings == ()
    assert analysis.score == 100
    assert analysis.severity is None


# ---------------------------------------------------------------------------
# Determinism: identical runs, byte for byte (modulo nothing — pure)
# ---------------------------------------------------------------------------


def test_analyze_requirement_is_deterministic() -> None:
    text = (
        "The system should support several payment methods and it must "
        "always be available. The account shall be created after registration."
    )
    first = analyze_requirement(text)
    assert len(first.findings) >= 4  # multi-detector text, not a trivial case
    for _ in range(3):
        assert analyze_requirement(text) == first
