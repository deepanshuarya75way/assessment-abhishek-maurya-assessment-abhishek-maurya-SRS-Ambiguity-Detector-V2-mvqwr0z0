"""Deterministic ambiguity engine (Stage 07): pure functions, zero network, zero LLM.

- `rules`: detector vocabularies + compiled patterns (the tunables).
- `detectors`: the 11 detectors + `Finding` + `REGISTRY` (fixed order).
- `engine`: dedup + transparent scoring + bands + health dimensions.

Same requirement + same code = same findings and score, always.
"""

from app.analysis.engine import (
    DEDUCTIONS,
    HEALTH_DIMENSIONS,
    RequirementAnalysis,
    analyze_requirement,
    band_for_score,
    deduplicate,
    health_for_findings,
    overall_score,
    score_findings,
    severity_counts,
    severity_of,
)

__all__ = [
    "DEDUCTIONS",
    "HEALTH_DIMENSIONS",
    "RequirementAnalysis",
    "analyze_requirement",
    "band_for_score",
    "deduplicate",
    "health_for_findings",
    "overall_score",
    "score_findings",
    "severity_counts",
    "severity_of",
]
