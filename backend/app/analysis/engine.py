"""Deterministic analysis engine (Stage 07): detectors → dedup → score.

Pure functions over text (zero I/O, zero network, zero LLM). The pipeline:

1. Run every detector in `REGISTRY` order over one requirement.
2. Sort findings by span, then dedup:
   - exact duplicates (same detector + same span) collapse to one;
   - identical spans from DIFFERENT detectors collapse to the highest severity
     (ties break by registry order — structural detectors win).
   Overlapping-but-distinct spans are KEPT: e.g. "quickly" (subjective-term)
   and "respond quickly" (missing-measurable-criteria) are genuinely different
   concerns — the word is vague AND the claim is untestable.
3. Score: 100 − Σ severity deductions, clamped to 0–100.
4. Requirement severity = highest finding severity (None when clean).
5. Analysis score = arithmetic mean of requirement scores (half-up rounding);
   band + 4 health dimensions derive from the same deductions — no hidden
   weighting anywhere. The score is a heuristic indicator, not a validated
   measurement (see `the project contract` §6).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.detectors import REGISTRY, Finding, Severity

# Transparent deduction table (PROJECT_SPEC §6 — the ONLY weighting in play).
DEDUCTIONS: dict[Severity, int] = {"low": 5, "medium": 10, "high": 15, "critical": 20}
_SEVERITY_RANK: dict[Severity, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_BASE_SCORE = 100

# Registry position per detector id — the deterministic dedup tie-break.
_DETECTOR_PRIORITY: dict[str, int] = {
    detector[0]: index for index, (detector, _) in enumerate(REGISTRY)
}

# Health dimensions (API_CONTRACT §4.3 `health`): each detector category feeds
# EXACTLY one dimension, so every point is traceable to its findings.
HEALTH_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "measurability": ("subjective-term", "missing-measurable-criteria"),
    "specificity": ("vague-quantifier", "undefined-terminology", "absolute-language"),
    "clarity": (
        "pronoun-reference",
        "ambiguous-operator",
        "optional-language",
        "passive-actor",
    ),
    "completeness": ("missing-constraint", "incomplete-requirement"),
}


@dataclass(frozen=True)
class RequirementAnalysis:
    """Scored findings for ONE requirement (offsets index its own text)."""

    findings: tuple[Finding, ...]
    score: int
    severity: Severity | None


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Collapse exact dupes + identical-span cross-detector overlaps.

    Input order is irrelevant: findings sort by (start, end, priority) first,
    so the survivor of every collapse is deterministic.
    """
    ordered = sorted(
        findings,
        key=lambda f: (f.start_offset, f.end_offset, _DETECTOR_PRIORITY[f.detector_id]),
    )
    kept: list[Finding] = []
    for finding in ordered:
        if not kept:
            kept.append(finding)
            continue
        prev = kept[-1]
        same_span = (
            finding.start_offset == prev.start_offset and finding.end_offset == prev.end_offset
        )
        if not same_span:
            kept.append(finding)
            continue
        if finding.detector_id == prev.detector_id:
            continue  # exact duplicate — keep the first
        # Identical span, different detectors: higher severity wins; the sort
        # already placed the higher-priority detector first on ties.
        if _SEVERITY_RANK[finding.severity] > _SEVERITY_RANK[prev.severity]:
            kept[-1] = finding
    return kept


def score_findings(findings: list[Finding] | tuple[Finding, ...]) -> int:
    """100 − Σ deductions, clamped to 0–100."""
    total = _BASE_SCORE - sum(DEDUCTIONS[f.severity] for f in findings)
    return max(0, min(_BASE_SCORE, total))


def severity_of(findings: list[Finding] | tuple[Finding, ...]) -> Severity | None:
    """Highest finding severity, or None when there are no findings."""
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity


def analyze_requirement(text: str) -> RequirementAnalysis:
    """Run all detectors over one requirement → deduped findings + score."""
    raw: list[Finding] = []
    for _, detect in REGISTRY:
        raw.extend(detect(text))
    findings = deduplicate(raw)
    return RequirementAnalysis(
        findings=tuple(findings),
        score=score_findings(findings),
        severity=severity_of(findings),
    )


def overall_score(requirement_scores: list[int]) -> int:
    """Arithmetic mean, half-up rounding (deterministic; banker's rounding
    would surprise: 72.5 must band as 73, not 72). Empty input → 100: no
    requirements means nothing was found wanting (unreachable in practice —
    empty analyses are refused before scoring)."""
    if not requirement_scores:
        return _BASE_SCORE
    return int(sum(requirement_scores) / len(requirement_scores) + 0.5)


def band_for_score(score: int) -> str:
    """Interpretation band (PROJECT_SPEC §6): low 80–100, moderate 60–79,
    high 40–59, very_high 0–39."""
    if score >= 80:
        return "low"
    if score >= 60:
        return "moderate"
    if score >= 40:
        return "high"
    return "very_high"


def health_for_findings(findings: list[Finding] | tuple[Finding, ...]) -> dict[str, int]:
    """Per-dimension 100 − Σ(mapped deductions), clamped. Every detector maps
    to exactly one dimension (see HEALTH_DIMENSIONS)."""
    dimension_of = {
        detector_id: dimension
        for dimension, detector_ids in HEALTH_DIMENSIONS.items()
        for detector_id in detector_ids
    }
    health = dict.fromkeys(HEALTH_DIMENSIONS, _BASE_SCORE)
    for finding in findings:
        dimension = dimension_of[finding.detector_id]
        health[dimension] -= DEDUCTIONS[finding.severity]
    return {dimension: max(0, value) for dimension, value in health.items()}


def severity_counts(findings: list[Finding] | tuple[Finding, ...]) -> dict[str, int]:
    """Per-severity finding totals (persisted in `score_breakdown.counts`)."""
    counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for finding in findings:
        counts[finding.severity] += 1
    return counts
