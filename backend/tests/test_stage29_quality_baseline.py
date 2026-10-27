"""Stage 29 pre-production QA baselines.

These tests intentionally sit above the earlier unit suites without replacing
or weakening them. They pin three high-risk regression surfaces that are easy
for future changes to disturb accidentally:

* the public API route surface (no undocumented route appears silently),
* a compact deterministic analysis golden corpus (segmentation + findings +
  scores + health), and
* AI prompt payload minimization/privacy for the documented "what was sent"
  claim (summaries and capped requirement excerpts, never provider keys or
  unrelated metadata).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.routing import APIRoute

from app.ai.prompts.improvement_v1 import render_improvement
from app.ai.prompts.overview_v1 import render_overview
from app.analysis.engine import (
    analyze_requirement,
    band_for_score,
    health_for_findings,
    overall_score,
    severity_counts,
)
from app.api.v1.router import api_router
from app.services.ai_enhancement import _improvement_payload, _overview_payload
from app.services.analysis import AnalysisDetail, IssueDetail, RequirementDetail
from app.services.segmentation import normalize_text, segment_requirements


@dataclass(frozen=True)
class GoldenCase:
    name: str
    text: str
    segments: tuple[tuple[str | None, str, str, int, int, int, int], ...]
    findings_by_requirement: tuple[tuple[tuple[str, str, str, int, int], ...], ...]
    requirement_scores: tuple[int, ...]
    overall_score: int
    band: str
    health: dict[str, int]
    severity_counts: dict[str, int]


GOLDEN_CASES = (
    GoldenCase(
        name="clear_requirements",
        text=(
            "FR-001: The system shall lock a user account for 15 minutes after "
            "5 failed login attempts.\n"
            "FR-002: The API shall return HTTP 200 with JSON within 2 seconds "
            "for valid status requests."
        ),
        segments=(
            (
                "FR-001",
                "requirement_id",
                "The system shall lock a user account for 15 minutes after "
                "5 failed login attempts.",
                8,
                90,
                1,
                1,
            ),
            (
                "FR-002",
                "requirement_id",
                "The API shall return HTTP 200 with JSON within 2 seconds for "
                "valid status requests.",
                99,
                182,
                2,
                2,
            ),
        ),
        findings_by_requirement=((), ()),
        requirement_scores=(100, 100),
        overall_score=100,
        band="low",
        health={"measurability": 100, "specificity": 100, "clarity": 100, "completeness": 100},
        severity_counts={"low": 0, "medium": 0, "high": 0, "critical": 0},
    ),
    GoldenCase(
        name="ambiguous_multi_pattern_requirement",
        text=(
            "The system should support several payment methods quickly, etc. "
            "It shall always be available and the account shall be created after registration."
        ),
        segments=(
            (
                None,
                "paragraph",
                "The system should support several payment methods quickly, etc. "
                "It shall always be available and the account shall be created "
                "after registration.",
                0,
                145,
                1,
                1,
            ),
        ),
        findings_by_requirement=(
            (
                ("optional-language", "low", "should", 11, 17),
                ("vague-quantifier", "medium", "several", 26, 33),
                ("missing-measurable-criteria", "high", "payment methods quickly", 34, 57),
                ("subjective-term", "medium", "quickly", 50, 57),
                ("ambiguous-operator", "high", "etc.", 59, 63),
                ("pronoun-reference", "medium", "It", 64, 66),
                ("absolute-language", "medium", "always", 73, 79),
                ("missing-measurable-criteria", "high", "available", 83, 92),
                ("passive-actor", "medium", "be created", 115, 125),
            ),
        ),
        requirement_scores=(0,),
        overall_score=0,
        band="very_high",
        health={"measurability": 60, "specificity": 80, "clarity": 60, "completeness": 100},
        severity_counts={"low": 1, "medium": 5, "high": 3, "critical": 0},
    ),
    GoldenCase(
        name="technical_edge_cases",
        text=(
            "REQ-9: Service URL https://api.example.com/v1/items?id=123 shall return 400 "
            "for malformed UUID values.\n"
            "- Retry when necessary.\n"
            "3.2 The gateway shall process requests."
        ),
        segments=(
            (
                "REQ-9",
                "requirement_id",
                "Service URL https://api.example.com/v1/items?id=123 shall return "
                "400 for malformed UUID values.",
                7,
                102,
                1,
                1,
            ),
            (None, "bullet", "Retry when necessary.", 105, 126, 2, 2),
            ("3.2", "decimal", "The gateway shall process requests.", 131, 166, 3, 3),
        ),
        findings_by_requirement=(
            (),
            (
                ("incomplete-requirement", "high", "Retry when necessary.", 0, 21),
                ("optional-language", "low", "when necessary", 6, 20),
            ),
            (("missing-constraint", "high", "process requests", 18, 34),),
        ),
        requirement_scores=(100, 80, 85),
        overall_score=88,
        band="low",
        health={"measurability": 100, "specificity": 100, "clarity": 95, "completeness": 70},
        severity_counts={"low": 1, "medium": 0, "high": 2, "critical": 0},
    ),
)


def test_documented_api_route_surface_is_stable() -> None:
    """All /api/v1 routes are intentionally documented in API_CONTRACT.

    If a route is added, this test should fail until API_CONTRACT, ownership,
    security posture, and frontend clients (where applicable) are reviewed.
    """

    actual = sorted(
        (next(iter(route.methods - {"HEAD", "OPTIONS"})), route.path)
        for route in api_router.routes
        if isinstance(route, APIRoute)
    )
    assert actual == sorted(
        [
            ("DELETE", "/ai/providers/{credential_id}"),
            ("DELETE", "/analysis/{analysis_id}"),
            ("DELETE", "/auth/account"),
            ("DELETE", "/documents/{document_id}"),
            ("GET", "/ai/providers"),
            ("GET", "/analysis"),
            ("GET", "/analysis/{analysis_id}"),
            ("GET", "/auth/me"),
            ("GET", "/dashboard"),
            ("GET", "/documents"),
            ("GET", "/documents/{document_id}"),
            ("GET", "/documents/{document_id}/download"),
            ("GET", "/health/live"),
            ("GET", "/health/ready"),
            ("GET", "/privacy/export/{export_id}"),
            ("GET", "/settings/privacy"),
            ("GET", "/settings/profile"),
            ("PATCH", "/ai/providers/{credential_id}"),
            ("PATCH", "/settings/privacy"),
            ("PATCH", "/settings/profile"),
            ("POST", "/ai/providers"),
            ("POST", "/ai/providers/{credential_id}/rotate-key"),
            ("POST", "/ai/providers/{credential_id}/test"),
            ("POST", "/analysis"),
            ("POST", "/analysis/{analysis_id}/retry-ai"),
            ("POST", "/auth/change-password"),
            ("POST", "/auth/forgot-password"),
            ("POST", "/auth/login"),
            ("POST", "/auth/logout"),
            ("POST", "/auth/refresh"),
            ("POST", "/auth/register"),
            ("POST", "/auth/resend-verification"),
            ("POST", "/auth/reset-password"),
            ("POST", "/auth/verify-email"),
            ("POST", "/documents/{document_id}/download-url"),
            ("POST", "/documents/upload"),
            ("POST", "/privacy/export"),
            ("POST", "/privacy/purge-history"),
        ]
    )


def test_deterministic_analysis_golden_corpus() -> None:
    for case in GOLDEN_CASES:
        normalized = normalize_text(case.text)
        segments = segment_requirements(normalized)
        assert [
            (
                item.identifier,
                item.strategy,
                item.text,
                item.start_offset,
                item.end_offset,
                item.line_start,
                item.line_end,
            )
            for item in segments
        ] == list(case.segments), case.name
        assert all(
            normalized[item.start_offset : item.end_offset] == item.text for item in segments
        )

        analyses = [analyze_requirement(item.text) for item in segments]
        assert [item.score for item in analyses] == list(case.requirement_scores), case.name
        assert [
            tuple(
                (f.detector_id, f.severity, f.phrase, f.start_offset, f.end_offset)
                for f in item.findings
            )
            for item in analyses
        ] == list(case.findings_by_requirement), case.name
        for segment, result in zip(segments, analyses, strict=True):
            for finding in result.findings:
                assert segment.text[finding.start_offset : finding.end_offset] == finding.phrase

        all_findings = [finding for result in analyses for finding in result.findings]
        overall = overall_score([item.score for item in analyses])
        assert overall == case.overall_score, case.name
        assert band_for_score(overall) == case.band, case.name
        assert health_for_findings(all_findings) == case.health, case.name
        assert severity_counts(all_findings) == case.severity_counts, case.name


def test_ai_prompt_payloads_are_minimized_and_do_not_include_secrets_or_metadata() -> None:
    secret_like_text = " ".join(
        ["sk-live-secret-value", "password" + "=CorrectHorse", "token=header.payload.signature"]
    )
    issue = IssueDetail(
        id=uuid.uuid4(),
        requirement_id=uuid.uuid4(),
        detector_id="subjective-term",
        category="Subjective term",
        severity="medium",
        phrase="quickly",
        start_offset=24,
        end_offset=31,
        reason="The phrase is subjective.",
        recommendation="Replace with a measurable response-time threshold.",
    )
    requirement = RequirementDetail(
        id=issue.requirement_id,
        position=0,
        identifier="REQ-SECRET",
        section="Hidden metadata section",
        text=(
            "The API shall respond quickly. "
            + secret_like_text
            + " This extra text represents sensitive requirement content."
        ),
        segmentation={"strategy": "requirement_id", "confidence": 0.95},
        score=90,
        severity="medium",
        issues_count=1,
        issues=(issue,),
    )
    detail = AnalysisDetail(
        id=uuid.uuid4(),
        title="Sensitive title must not enter overview prompt",
        status="analyzed",
        source_type="text",
        score=90,
        band="low",
        score_breakdown={},
        health={"clarity": 100},
        requirements_count=1,
        issues_count=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        requirements=(requirement,),
    )

    overview_text = render_overview(_overview_payload(detail))
    assert "Sensitive title" not in overview_text
    assert "REQ-SECRET" not in overview_text
    assert "Hidden metadata" not in overview_text
    assert secret_like_text not in overview_text
    assert "quickly" in overview_text  # finding summary is deliberately included
    assert "The phrase is subjective." in overview_text

    improvement_text = render_improvement(_improvement_payload(requirement))
    assert "REQ-SECRET" not in improvement_text
    assert "Hidden metadata" not in improvement_text
    assert secret_like_text in improvement_text  # the current requirement under rewrite is the data
    assert "quickly" in improvement_text


def test_ai_improvement_payload_caps_requirement_text_and_findings() -> None:
    long_requirement = "A" * 4500
    findings = tuple(
        IssueDetail(
            id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            detector_id=f"detector-{index}",
            category=f"Category {index}",
            severity="low",
            phrase="x" * 600,
            start_offset=0,
            end_offset=1,
            reason="r" * 1200,
            recommendation="recommendation",
        )
        for index in range(12)
    )
    requirement = RequirementDetail(
        id=uuid.uuid4(),
        position=0,
        identifier=None,
        section=None,
        text=long_requirement,
        segmentation={},
        score=0,
        severity="low",
        issues_count=len(findings),
        issues=findings,
    )

    payload = _improvement_payload(requirement)
    assert len(payload.requirement_text) == 4000
    assert len(payload.findings) == 8
    assert all(len(item.phrase) == 500 for item in payload.findings)
    assert all(len(item.reason) == 1000 for item in payload.findings)
