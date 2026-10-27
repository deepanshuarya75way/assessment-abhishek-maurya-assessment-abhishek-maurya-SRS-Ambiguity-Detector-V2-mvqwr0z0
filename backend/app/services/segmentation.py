"""Deterministic SRS normalization + requirement segmentation (PROJECT_SPEC §9).

Pure functions: normalized text in, ordered segments out. No I/O, no network,
no randomness — identical input ALWAYS yields identical segments (pinned by
`tests/test_segmentation.py`, including re-segmentation of stored `source_text`
reproducing the persisted rows).

Pipeline
--------
1. `normalize_text` — line-ending unification, BOM/zero-width stripping,
   trailing-whitespace stripping, 3+-blank-line collapse, edge blank-line
   stripping. Meaning-preserving ONLY: no case/Unicode folding, no spell
   fixes, tabs and inner spacing untouched.
2. `segment_requirements` — one deterministic pass over the normalized text:
   each line is a requirement marker (requirement-ID / decimal / numbered /
   bullet), a heading (`#`-style, decimal/numbered short lines, dot-less
   `3 Title` lines, ALL-CAPS — kept as section context, never requirements), or
   paragraph text (accepted as a requirement ONLY with a requirement-language
   signal). Marker lines absorb continuation lines (indented, or following an
   unterminated sentence); blank lines and new markers/headings terminate.

Marker discipline: every marker needs whitespace after it (`1. `, `- `, …) —
a marker glued to text (`1.The system`) degrades to a paragraph candidate
instead of mis-splitting. A paragraph is ONE requirement even when
multi-sentence (sentence-splitting is future work, not silent guessing).

Confidence scale (honest, documented — these are segmentation confidences,
NOT ambiguity scores): requirement-ID 0.95; decimal/numbered 0.90 (strong
signal) / 0.75 (weak) / 0.60 (none); bullet 0.80 / 0.65 / 0.50; paragraph
0.55 (strong) / 0.50 (imperative-only).

Known limits: sentence-level splitting inside paragraphs, tables/figures, and
non-English modal verbs are out of scope (see STAGE_STATUS).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SegmentationStrategy = Literal["requirement_id", "decimal", "numbered", "bullet", "paragraph"]

# Refuse past this many segments (400 `text_too_large` with counts) — the
# service NEVER silently truncates an over-long analysis.
MAX_REQUIREMENTS = 2000
# Mirrors `requirements.section` VARCHAR(200): over-long heading paths are cut.
SECTION_MAX_LENGTH = 200
# Numbered/decimal lines at least this long count as requirements even without
# a modal signal (a 60+ char numbered line is a statement, not a heading).
LONG_LINE_CHARS = 60

_ZERO_WIDTH_RE = re.compile("[\u200b-\u200d\ufeff]")
_BLANK_RUN_RE = re.compile(r"\n{4,}")  # 3+ blank lines collapse to 2

# Explicit requirement IDs: FR-001, NFR-12, REQ001, BR-4, UR-2.1, UC-01, ...
# Case-insensitive match, stored VERBATIM (source fidelity); total length is
# regex-capped under the VARCHAR(32) column.
_ID_CORE = r"(?:FR|NFR|REQ|BR|UR|SRS|UC|AC|TC)[-_ ]?\d[\dA-Za-z.\-_]{0,24}"
_REQ_ID_RE = re.compile(rf"^({_ID_CORE})(?:\s*[:\-–—.)]+\s*|\s+)(.*)$", re.IGNORECASE)
# Bare ID on its own line ("FR-001") — the body MUST follow on later lines.
_REQ_ID_BARE_RE = re.compile(rf"^({_ID_CORE})\s*[:\-–—.)]?\s*$", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"^(\d{1,4}(?:\.\d{1,4}){1,5})\.?\s+(.*)$")
_NUMBERED_DOT_RE = re.compile(r"^(\d{1,4})\.\s+(.*)$")
_NUMBERED_PAREN_RE = re.compile(r"^(\d{1,4})\)\s+(.*)$")
# Dot-less numbered heading ("3 Functional Requirements"): digit-led, Title-case
# rest, no sentence punctuation, short — and NO requirement signal (a signal
# promotes the line to a paragraph requirement instead; see _is_dotless_heading).
_DOTLESS_HEADING_RE = re.compile(r"^\d{1,4}\s+([A-Z][^.!?…]{1,58})$")
_BULLET_RE = re.compile(r"^([-*+•▪◦])(?!\1)\s+(.*)$")
_PAREN_BULLET_RE = re.compile(r"^\(([A-Za-z0-9]{1,6})\)\s+(.*)$")
_HASH_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# STRONG: modal/necessity verbs — the ONLY signals that promote a plain
# paragraph to a requirement. WEAK: future-tense + action verbs — modulate
# marker confidence only (a "will be updated" sentence is prose, not a req).
_STRONG_SIGNAL_RE = re.compile(
    r"\b(shall|must|should|(?:is|are) required to|needs? to|ha(?:s|ve) to)\b",
    re.IGNORECASE,
)
_WEAK_SIGNAL_RE = re.compile(
    r"\b(will|may|might|could|can|provides?|supports?|allows?|enables?|"
    r"displays?|shows?|stores?|saves?|validates?|ensures?|includes?|"
    r"contains?|requires?|handles?|process(?:es|ed)?|generates?|"
    r"accepts?|rejects?)\b",
    re.IGNORECASE,
)
# Sentence-initial action verb ("Display an error message.") — promotes a
# paragraph at the lowest confidence. Deliberately small verb list.
_IMPERATIVE_RE = re.compile(
    r"^(Provide|Display|Show|Store|Save|Validate|Ensure|Support|Allow|Enable|"
    r"Require|Include|Handle|Process|Send|Receive|Generate|Create|Delete|Update|"
    r"Return|Accept|Reject|Log|Encrypt|Authenticate|Authorize)\b"
)

# A sentence ending in one of these is COMPLETE: an unindented next line starts
# something new instead of continuing. (":" is NOT terminal — it introduces.)
_TERMINAL_PUNCT = frozenset(".?!;…")


@dataclass(frozen=True)
class Segment:
    """One detected requirement. `text` is the EXACT normalized-text span
    `[start_offset:end_offset)` (marker prefix excluded, internal newlines
    preserved) — the invariant `normalized[start:end] == text` always holds."""

    text: str
    identifier: str | None
    section: str | None
    strategy: SegmentationStrategy
    confidence: float
    start_offset: int
    end_offset: int
    line_start: int  # 1-based, inclusive
    line_end: int  # 1-based, inclusive


def normalize_text(raw: str) -> str:
    """Conservative normalization (see module docstring). Blank input → `""`."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH_RE.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_RUN_RE.sub("\n\n\n", text)
    return text.strip("\n")


def _has_strong_signal(text: str) -> bool:
    return _STRONG_SIGNAL_RE.search(text) is not None


def _has_weak_signal(text: str) -> bool:
    return _WEAK_SIGNAL_RE.search(text) is not None


def _is_caps_heading(line: str) -> bool:
    """ALL-CAPS short line without sentence punctuation ("ACCEPTANCE CRITERIA").

    Lines carrying a STRONG signal are requirements even when shouted, so the
    caller checks markers/signals first — this is a last-resort heading test.
    """
    stripped = line.strip()
    if not 2 <= len(stripped) <= 80:
        return False
    if stripped[-1] in ".!?…":
        return False
    letters = [char for char in stripped if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def _dotless_heading_title(line: str) -> str | None:
    """Title of a dot-less numbered heading, or None (signal-bearing lines are
    requirements-in-waiting, never headings — the signal check is the point)."""
    stripped = line.strip()
    match = _DOTLESS_HEADING_RE.match(stripped)
    if not match:
        return None
    if _has_strong_signal(stripped) or _has_weak_signal(stripped):
        return None
    return match.group(1)


def _is_marker_or_heading(line: str) -> bool:
    """True for any line that TERMINATES an open requirement or paragraph run:
    headings of any kind plus every requirement-marker style."""
    stripped = line.strip()
    if not stripped:
        return False
    if _HASH_HEADING_RE.match(stripped):
        return True
    if _REQ_ID_RE.match(stripped) or _REQ_ID_BARE_RE.match(stripped):
        return True
    if (
        _DECIMAL_RE.match(stripped)
        or _NUMBERED_DOT_RE.match(stripped)
        or _NUMBERED_PAREN_RE.match(stripped)
        or _BULLET_RE.match(stripped)
        or _PAREN_BULLET_RE.match(stripped)
        or _dotless_heading_title(line) is not None
    ):
        return True
    return _is_caps_heading(stripped) and not _has_strong_signal(stripped)


def _confidence(strategy: SegmentationStrategy, *, strong: bool, weak: bool) -> float:
    if strategy == "requirement_id":
        return 0.95
    if strategy == "decimal" or strategy == "numbered":
        return 0.90 if strong else 0.75 if weak else 0.60
    if strategy == "bullet":
        return 0.80 if strong else 0.65 if weak else 0.50
    return 0.55 if strong else 0.50  # paragraph


def _content_bounds(line: str) -> tuple[int, int] | None:
    """`(start_col, end_col)` of the stripped content, or None when blank."""
    stripped = line.strip()
    if not stripped:
        return None
    start = len(line) - len(line.lstrip())
    return (start, start + len(stripped))


def _rest_col(line: str, match: re.Match[str], group: int) -> int:
    """Absolute column where capture `group` starts (`match` ran on the
    stripped line — measuring from the match, not `str.index`, keeps
    marker-echo rests like `1. 1` honest)."""
    return len(line) - len(line.lstrip()) + match.start(group)


def _consume_continuation(
    lines: list[str], first: int, prev_text: str, *, force_first: bool
) -> int:
    """Extend a requirement past line `first`; return the first line index NOT
    part of it. A following line joins while it is non-blank, not a
    marker/heading, and (indented OR the previous line is unterminated) —
    except `force_first` joins the first body line unconditionally (bare-ID and
    empty-rest markers, whose text lives entirely below the marker)."""
    index = first + 1
    previous = prev_text
    force = force_first
    while index < len(lines):
        candidate = lines[index]
        if not candidate.strip() or _is_marker_or_heading(candidate):
            break
        indented = candidate[:1] in (" ", "\t")
        terminated = previous[-1:] in _TERMINAL_PUNCT
        if not (force or indented or not terminated):
            break
        force = False
        previous = candidate.strip()
        index += 1
    return index


def segment_requirements(normalized: str) -> list[Segment]:
    """Segment NORMALIZED text (see `normalize_text`) into requirements.

    Markers win over signals (a `FR-001` line is a requirement even without a
    modal verb); bare text needs a signal. Headings update the section stack.
    """
    if not normalized:
        return []
    lines = normalized.split("\n")
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    sections: list[tuple[int, str]] = []
    segments: list[Segment] = []

    def section_path() -> str | None:
        if not sections:
            return None
        return " > ".join(title for _, title in sections)[:SECTION_MAX_LENGTH]

    def push_heading(level: int, title: str) -> None:
        title = title.strip()
        if not title:
            return
        while sections and sections[-1][0] >= level:
            sections.pop()
        sections.append((level, title))

    def emit(
        strategy: SegmentationStrategy,
        identifier: str | None,
        first: int,
        first_col: int,
        last: int,
        joined_text: str,
    ) -> None:
        bounds = _content_bounds(lines[last])
        assert bounds is not None  # last line is always non-blank by construction
        segments.append(
            Segment(
                text=normalized[offsets[first] + first_col : offsets[last] + bounds[1]],
                identifier=identifier,
                section=section_path(),
                strategy=strategy,
                confidence=_confidence(
                    strategy,
                    strong=_has_strong_signal(joined_text),
                    weak=_has_weak_signal(joined_text),
                ),
                start_offset=offsets[first] + first_col,
                end_offset=offsets[last] + bounds[1],
                line_start=first + 1,
                line_end=last + 1,
            )
        )

    def joined_range(first: int, end: int) -> str:
        return " ".join(lines[i].strip() for i in range(first, end))

    def requirement_or_heading(
        index: int,
        identifier: str,
        rest: str,
        rest_col: int,
        *,
        strategy: SegmentationStrategy,
        heading_level: int,
    ) -> int:
        """Shared decimal/numbered rule: signal-or-long → requirement, else the
        line is a heading. Returns the first unconsumed line index."""
        if _has_strong_signal(rest) or _has_weak_signal(rest) or len(rest) >= LONG_LINE_CHARS:
            end = _consume_continuation(lines, index, rest, force_first=False)
            emit(strategy, identifier, index, rest_col, end - 1, joined_range(index, end))
            return end
        push_heading(heading_level, rest)
        return index + 1

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        heading = _HASH_HEADING_RE.match(stripped)
        if heading:
            push_heading(len(heading.group(1)), heading.group(2))
            index += 1
            continue

        req_match = _REQ_ID_RE.match(stripped)
        bare_match = None if req_match else _REQ_ID_BARE_RE.match(stripped)
        if req_match is not None or bare_match is not None:
            match = req_match if req_match is not None else bare_match
            assert match is not None
            identifier = match.group(1).rstrip(".-_")
            rest = req_match.group(2).strip() if req_match else ""
            if rest:
                assert req_match is not None
                end = _consume_continuation(lines, index, rest, force_first=False)
                emit(
                    "requirement_id",
                    identifier,
                    index,
                    _rest_col(line, req_match, 2),
                    end - 1,
                    joined_range(index, end),
                )
            else:
                end = _consume_continuation(lines, index, "", force_first=True)
                if end == index + 1:
                    index = end  # bare ID with no body: not a requirement
                    continue
                first_bounds = _content_bounds(lines[index + 1])
                assert first_bounds is not None
                emit(
                    "requirement_id",
                    identifier,
                    index + 1,
                    first_bounds[0],
                    end - 1,
                    joined_range(index, end),
                )
            index = end
            continue

        decimal = _DECIMAL_RE.match(stripped)
        if decimal:
            index = requirement_or_heading(
                index,
                decimal.group(1),
                decimal.group(2).strip(),
                _rest_col(line, decimal, 2),
                strategy="decimal",
                heading_level=decimal.group(1).count(".") + 1,
            )
            continue

        numbered = _NUMBERED_DOT_RE.match(stripped)
        if numbered:
            index = requirement_or_heading(
                index,
                numbered.group(1),
                numbered.group(2).strip(),
                _rest_col(line, numbered, 2),
                strategy="numbered",
                heading_level=1,
            )
            continue

        paren = _NUMBERED_PAREN_RE.match(stripped)
        bullet = _BULLET_RE.match(stripped)
        paren_bullet = _PAREN_BULLET_RE.match(stripped)
        if paren is not None or bullet is not None or paren_bullet is not None:
            match = paren if paren is not None else bullet if bullet is not None else paren_bullet
            assert match is not None
            rest = match.group(2).strip()  # rest is group 2 in all three patterns
            if not rest:
                index += 1  # lone marker with no text: skip
                continue
            rest_col = _rest_col(line, match, 2)
            strategy: SegmentationStrategy = "numbered" if paren is not None else "bullet"
            marker_id = paren.group(1) if paren is not None else None
            end = _consume_continuation(lines, index, rest, force_first=False)
            emit(strategy, marker_id, index, rest_col, end - 1, joined_range(index, end))
            index = end
            continue

        dotless = _dotless_heading_title(line)
        if dotless is not None:
            push_heading(1, dotless)
            index += 1
            continue

        if _is_caps_heading(stripped) and not _has_strong_signal(stripped):
            push_heading(1, stripped)
            index += 1
            continue

        # Paragraph run: consecutive non-blank, non-marker lines form ONE block.
        end = index + 1
        while end < len(lines) and lines[end].strip() and not _is_marker_or_heading(lines[end]):
            end += 1
        first_bounds = _content_bounds(line)
        assert first_bounds is not None
        joined = joined_range(index, end)
        if _has_strong_signal(joined) or _IMPERATIVE_RE.match(lines[index].strip()):
            emit("paragraph", None, index, first_bounds[0], end - 1, joined)
        index = end

    return segments
