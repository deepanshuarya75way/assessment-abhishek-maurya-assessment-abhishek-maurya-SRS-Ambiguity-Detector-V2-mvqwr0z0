"""The 11 deterministic ambiguity detectors (Stage 07).

Each detector is a pure function over requirement text — no I/O, no network,
no LLM, no randomness. Inputs and outputs are fully typed (`Finding`); every
finding carries requirement-relative `[start, end)` offsets into the text it
was detected in (the DB contract: highlights index `requirements.text`).

Conventions shared by all detectors:
- Word-boundary matching only (no substring accidents).
- Conservative firing: a guard that is wrong suppresses a true positive, but a
  missing guard manufactures distrust — every guard is documented + tested.
- "Potential ambiguity" language in reasons where the rule is heuristic
  (pronouns, passives, undefined terms, missing structure).
- Severities are fixed per detector/pattern (see `engine.DEDUCTIONS`); the
  per-pattern table is documented in `the project contract` §5.

Detector priority (`REGISTRY` order) also settles dedup ties in the engine:
structural detectors first, wording detectors last.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.analysis import rules

Severity = Literal["low", "medium", "high", "critical"]

# Stable detector ids (kebab-case, matching the API_CONTRACT §4.3 example
# `vague-quantifier`) + human categories for the UI.
VAGUE_QUANTIFIER = ("vague-quantifier", "Vague quantifiers")
SUBJECTIVE_TERM = ("subjective-term", "Subjective terms")
MISSING_MEASURABLE = ("missing-measurable-criteria", "Missing measurable criteria")
PRONOUN_REFERENCE = ("pronoun-reference", "Pronoun references")
OPTIONAL_LANGUAGE = ("optional-language", "Optional language")
AMBIGUOUS_OPERATOR = ("ambiguous-operator", "Ambiguous operators")
UNDEFINED_TERM = ("undefined-terminology", "Undefined terminology")
ABSOLUTE_LANGUAGE = ("absolute-language", "Absolute language")
PASSIVE_ACTOR = ("passive-actor", "Passive voice / unclear actor")
MISSING_CONSTRAINT = ("missing-constraint", "Missing constraints")
INCOMPLETE_REQUIREMENT = ("incomplete-requirement", "Incomplete requirements")


@dataclass(frozen=True)
class Finding:
    """One detector hit. `phrase` is the EXACT requirement-text span
    `[start_offset:end_offset)` — highlighting slices it verbatim."""

    detector_id: str
    category: str
    severity: Severity
    phrase: str
    start_offset: int
    end_offset: int
    reason: str
    recommendation: str


# ---------------------------------------------------------------------------
# Shared matching helpers
# ---------------------------------------------------------------------------

_SENTENCE_END_RE = re.compile(r"[.!?…]+|\n+")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")
_NON_PRONOUN_CAPITALS = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "them",
        "their",
        "he",
        "she",
        "his",
        "her",
        "him",
        "our",
        "your",
        "my",
        "we",
        "you",
        "i",
    }
)


def _sentences(text: str) -> list[tuple[int, int, str]]:
    """Coarse sentence split with offsets: split on terminal punctuation runs
    and newlines. Deterministic; abbreviations (`e.g.`) may split — accepted,
    the detectors using this only need same-sentence *presence* checks."""
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(text):
        end = match.start()
        piece = text[start:end].strip()
        if piece:
            leading = text[start:end].index(piece[0])
            spans.append((start + leading, start + leading + len(piece), piece))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        leading = text[start:].index(tail[0])
        spans.append((start + leading, start + leading + len(tail), tail))
    return spans


def _words(text: str) -> list[tuple[str, int, int]]:
    """Word tokens with offsets (hyphenated/apostrophe words stay whole)."""
    return [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]


def _phrase_pattern(phrases: tuple[str, ...], *, case_sensitive: bool = False) -> re.Pattern[str]:
    """Alternation for vocabulary phrases: longest-first, flexible inner
    whitespace, word-edge guarded (`(?!\\w)` also suits trailing punctuation
    like `etc.` where `\\b` could never match)."""
    ordered = sorted(phrases, key=len, reverse=True)
    alt = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in ordered)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<!\w)(?:" + alt + r")(?!\w)", flags)


def _find_phrases(
    text: str, phrases: tuple[str, ...], *, case_sensitive: bool = False
) -> list[tuple[int, int, str]]:
    pattern = _phrase_pattern(phrases, case_sensitive=case_sensitive)
    return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]


def _make_finding(
    detector: tuple[str, str],
    severity: Severity,
    text: str,
    start: int,
    end: int,
    reason: str,
    recommendation: str,
) -> Finding:
    return Finding(
        detector_id=detector[0],
        category=detector[1],
        severity=severity,
        phrase=text[start:end],
        start_offset=start,
        end_offset=end,
        reason=reason,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# 1. vague-quantifier (MEDIUM)
# ---------------------------------------------------------------------------

_BOUNDED_QUANTITY_RE = re.compile(
    r"\bas\s+(?:"
    + "|".join(re.escape(q).replace(r"\ ", r"\s+") for q in rules.VAGUE_QUANTIFIERS)
    + r")\s+as\b",
    re.IGNORECASE,
)


def detect_vague_quantifier(text: str) -> list[Finding]:
    """Bare quantity words (`several`, `many`, …). Skips the bounded frame
    "as <q> as <n>" (`as many as 5`) — an explicit amount, not vague."""
    bounded = [m.span() for m in _BOUNDED_QUANTITY_RE.finditer(text)]
    findings: list[Finding] = []
    for start, end, matched in _find_phrases(text, rules.VAGUE_QUANTIFIERS):
        if any(b_start <= start and end <= b_end for b_start, b_end in bounded):
            continue
        findings.append(
            _make_finding(
                VAGUE_QUANTIFIER,
                "medium",
                text,
                start,
                end,
                f'The quantity "{matched}" is not defined — implementers may '
                "assume different amounts.",
                f'Replace "{matched}" with an explicit quantity, range, or '
                "enumerated list of what is required.",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 2. subjective-term (MEDIUM)
# ---------------------------------------------------------------------------


def detect_subjective_term(text: str) -> list[Finding]:
    """Quality words with no intrinsic measurable definition (`fast`,
    `user-friendly`, …). Skips sentences that anchor the term to an external
    definition (`as defined in …`)."""
    findings: list[Finding] = []
    for s_start, _s_end, sentence in _sentences(text):
        if rules.EXTERNAL_DEFINITION_RE.search(sentence):
            continue
        for start, end, matched in _find_phrases(sentence, rules.SUBJECTIVE_TERMS):
            findings.append(
                _make_finding(
                    SUBJECTIVE_TERM,
                    "medium",
                    text,
                    s_start + start,
                    s_start + end,
                    f'"{matched}" is subjective — different readers may interpret '
                    "it differently, and it states no measurable criterion.",
                    f'Replace "{matched}" with an objective, testable criterion '
                    "(or reference the definition it must satisfy).",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 3. missing-measurable-criteria (HIGH)
# ---------------------------------------------------------------------------

_CLAIM_STOP_WORDS = (
    frozenset(rules.DANGLING_MODALS) | frozenset(rules.BE_VERBS) | {"might", "could"}
)


def detect_missing_measurable(text: str) -> list[Finding]:
    """A quality claim with no numeric threshold in the same sentence. The
    flagged span is the CLAIM (signal + up to two preceding words, e.g.
    "respond quickly") — deliberately wider than the subjective-term word so
    both findings survive dedup (they are different concerns: the word is
    vague AND the claim is untestable)."""
    findings: list[Finding] = []
    for s_start, _, sentence in _sentences(text):
        if rules.THRESHOLD_RE.search(sentence):
            continue
        tokens = _words(sentence)
        for start, end, _ in _find_phrases(sentence, rules.MEASURABLE_SIGNALS):
            # Claim window: up to two preceding words, stopping at modals and
            # be-verbs ("should respond quickly" → "respond quickly").
            window: list[tuple[str, int, int]] = []
            for token in reversed([t for t in tokens if t[2] <= start]):
                if token[0].lower() in _CLAIM_STOP_WORDS or len(window) == 2:
                    break
                window.append(token)
            claim_start = window[-1][1] if window else start
            claim = sentence[claim_start:end]
            findings.append(
                _make_finding(
                    MISSING_MEASURABLE,
                    "high",
                    text,
                    s_start + claim_start,
                    s_start + end,
                    f'The claim "{claim}" expresses a quality with no measurable '
                    'threshold — what counts as "acceptable" is undefined.',
                    "Add an objective threshold (response time, throughput, "
                    "percentage, limit) with the conditions it applies under.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 4. optional-language (LOW)
# ---------------------------------------------------------------------------

_MODAL_SET = frozenset(rules.OPTIONAL_MODALS)


def detect_optional_language(text: str) -> list[Finding]:
    """Modals + hedges that leave commitment unclear. Guards: `May <year>`
    (a month, not a modal) and `could not` (past inability, not uncertainty).
    `shall`/`must`/`will` never fire; `can` reads as permission, not doubt."""
    tokens = _words(text)
    next_after: dict[int, str] = {}
    for i, (_, _, w_end) in enumerate(tokens):
        next_after[w_end] = tokens[i + 1][0] if i + 1 < len(tokens) else ""
    findings: list[Finding] = []
    phrases = rules.OPTIONAL_MODALS + rules.OPTIONAL_HEDGES
    for start, end, matched in _find_phrases(text, phrases):
        lowered = matched.lower()
        following = next_after.get(end, "")
        if lowered == "may" and re.fullmatch(r"\d{4}", following):
            continue
        if lowered == "could" and following.lower() == "not":
            continue
        if lowered in _MODAL_SET:
            reason = (
                f'"{matched}" leaves the commitment unclear — clarify whether '
                "this grants permission, states a recommendation, or expresses "
                "uncertainty."
            )
            recommendation = (
                'Use "shall" for mandatory behavior, or state the condition or '
                "permission explicitly."
            )
        else:
            reason = (
                f'"{matched}" makes this requirement conditional or optional '
                "without saying when it applies."
            )
            recommendation = (
                "Name the condition explicitly, or split this into a requirement "
                "plus its conditions."
            )
        findings.append(
            _make_finding(OPTIONAL_LANGUAGE, "low", text, start, end, reason, recommendation)
        )
    return findings


# ---------------------------------------------------------------------------
# 5. pronoun-reference (MEDIUM, LOW for bare demonstratives)
# ---------------------------------------------------------------------------


def _referent_candidates(tokens: list[tuple[str, int, int]]) -> set[str]:
    """Distinct noun-ish words: domain + human nouns (any case) plus other
    capitalized words (articles, determiners, and pronouns excluded)."""
    found: set[str] = set()
    for word, _, _ in tokens:
        lowered = word.lower()
        if lowered in rules.DOMAIN_NOUNS or lowered in rules.HUMAN_NOUNS:
            found.add(lowered)
        elif word[0].isupper() and lowered not in _NON_PRONOUN_CAPITALS:
            found.add(lowered)
    return found


def detect_pronoun_reference(text: str) -> list[Finding]:
    """Unclear referents. `it` fires with 2+ preceding candidates; `they`
    passes with exactly one human candidate (brief §10 acceptable case);
    `he`/`she` always fire; bare demonstratives (`This is …`) fire LOW while
    noun-modifying ones (`this report`) pass. All-caps `IT` is skipped."""
    tokens = _words(text)
    findings: list[Finding] = []
    vocab = (
        rules.PRONOUNS_IT
        + rules.PRONOUNS_THEY
        + rules.PRONOUNS_GENDERED
        + rules.PRONOUNS_DEMONSTRATIVE
    )
    for start, end, matched in _find_phrases(text, vocab):
        if matched == "IT":  # all-caps: Information Technology, not a pronoun
            continue
        lowered = matched.lower()
        preceding = [t for t in tokens if t[2] <= start]
        following = [t for t in tokens if t[1] >= end]
        candidates = _referent_candidates(preceding)
        severity: Severity
        if lowered in rules.PRONOUNS_IT:
            if len(candidates) < 2:
                continue
            severity = "medium"
        elif lowered in rules.PRONOUNS_THEY:
            humans = {c for c in candidates if c in rules.HUMAN_NOUNS}
            if len(humans) == 1:
                continue
            severity = "medium"
        elif lowered in rules.PRONOUNS_GENDERED:
            severity = "medium"
        else:  # bare demonstrative ("This is …") vs noun-modifying ("this report")
            next_word = following[0][0].lower() if following else ""
            if following and next_word not in rules.VERBISH_AFTER_DEMONSTRATIVE:
                continue
            severity = "low"
        findings.append(
            _make_finding(
                PRONOUN_REFERENCE,
                severity,
                text,
                start,
                end,
                f'"{matched}" may refer to more than one thing — the intended '
                "referent is unclear.",
                f'Replace "{matched}" with the specific noun it refers to.',
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 6. ambiguous-operator (HIGH multiword, LOW bare `or` / `as well as`)
# ---------------------------------------------------------------------------

_LIST_OR_RE = re.compile(r",[^,;\n]+,[^,;\n]*\bor\b", re.IGNORECASE)
_BARE_OR_RE = re.compile(r"(?<!\w)or(?!\w)", re.IGNORECASE)
_BARE_AND_RE = re.compile(r"(?<!\w)and(?!\w)", re.IGNORECASE)

_OPERATOR_COPY: dict[str, tuple[Severity, str, str]] = {
    "and/or": (
        "high",
        '"and/or" does not say whether both are required or either is acceptable.',
        'State explicitly whether both options are required ("and"), either is '
        'acceptable ("or"), or each case behaves differently.',
    ),
    "etc": (
        "high",
        '"etc." leaves the scope open — the requirement never finishes its list.',
        "Enumerate every required item; remove open-ended list tails.",
    ),
    "and so on": (
        "high",
        '"and so on" leaves the scope open — the requirement never finishes.',
        "Enumerate every required case explicitly instead of trailing off.",
    ),
    "as well as": (
        "low",
        '"as well as" leaves it unclear whether the added item is also required.',
        'Clarify whether the added item is required too ("and") or background.',
    ),
    "or": (
        "low",
        'Bare "or" leaves the alternatives unclear — state whether any, all, or '
        "a specific combination is required.",
        "Name the alternatives explicitly and say whether the choice is "
        'inclusive ("any"), exclusive ("exactly one"), or ordered.',
    ),
}


def detect_ambiguous_operator(text: str) -> list[Finding]:
    """Open-ended operators. Multiword entries fire directly; bare `or` fires
    only for 3+ alternative lists (`A, B, or C`) or `and`/`or` mixes (precedence
    ambiguity) — never beside explicit `either`/`whether`."""
    findings: list[Finding] = []
    entries = [op for op, _ in rules.MULTIWORD_OPERATORS]
    for start, end, matched in _find_phrases(text, tuple(entries)):
        key = matched.lower().rstrip(".")
        severity, reason, recommendation = _OPERATOR_COPY[key]
        findings.append(
            _make_finding(AMBIGUOUS_OPERATOR, severity, text, start, end, reason, recommendation)
        )
    multiword_spans = [(f.start_offset, f.end_offset) for f in findings]
    for s_start, _, sentence in _sentences(text):
        if rules.EXPLICIT_ALTERNATION_RE.search(sentence):
            continue
        or_hits = list(_BARE_OR_RE.finditer(sentence))
        if not or_hits:
            continue
        has_and = _BARE_AND_RE.search(sentence) is not None
        has_list = _LIST_OR_RE.search(sentence) is not None
        if not (has_and or has_list):
            continue
        for hit in or_hits:
            start, end = s_start + hit.start(), s_start + hit.end()
            if any(s <= start and end <= e for s, e in multiword_spans):
                continue  # inside `and/or` — the HIGH finding already covers it
            severity, reason, recommendation = _OPERATOR_COPY["or"]
            findings.append(
                _make_finding(
                    AMBIGUOUS_OPERATOR, severity, text, start, end, reason, recommendation
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 7. undefined-terminology (LOW)
# ---------------------------------------------------------------------------

_STANDARD_CONTEXT_PRE = frozenset(
    {"industry", "coding", "security", "company", "organizational", "applicable"}
)
_STANDARD_CONTEXT_POST = frozenset({"compliant", "compliance"})


def detect_undefined_terminology(text: str) -> list[Finding]:
    """Qualifiers modifying a following word (`standard security`, `normal
    load`). Bare nouns (`comply with the standard`) do NOT fire. `standard`
    with an explicit frame (`industry standard`, `standard-compliant`) passes."""
    findings: list[Finding] = []
    for s_start, _s_end, sentence in _sentences(text):
        tokens = _words(sentence)
        for start, end, matched in _find_phrases(sentence, rules.UNDEFINED_QUALIFIERS):
            if text[s_start + end : s_start + end + 1] == "-":
                continue  # hyphen compound (`standard-compliant`) — a set term
            following = [t for t in tokens if t[1] >= end]
            if not following:
                continue
            lowered = matched.lower()
            if lowered == "standard":
                preceding = [t for t in tokens if t[2] <= start]
                prev_word = preceding[-1][0].lower() if preceding else ""
                if prev_word in _STANDARD_CONTEXT_PRE:
                    continue
                if following[0][0].lower() in _STANDARD_CONTEXT_POST:
                    continue
            findings.append(
                _make_finding(
                    UNDEFINED_TERM,
                    "low",
                    text,
                    s_start + start,
                    s_start + end,
                    f'"{matched}" may be undefined here — different readers may '
                    "assume different meanings.",
                    f'Define "{matched}" or reference the definition (policy, '
                    "glossary, section) it must satisfy.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 8. absolute-language (MEDIUM strong, LOW `any`/`all`)
# ---------------------------------------------------------------------------

_TIME_UNITS = frozenset(
    {
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "hour",
        "hours",
        "minute",
        "minutes",
        "second",
        "seconds",
    }
)


def detect_absolute_language(text: str) -> list[Finding]:
    """Absolutes that usually need an explicit boundary. Guards: bounded sets
    (`any of the following`, `all listed`) pass; scheduled `every <time-unit>`
    passes; `instant messaging` (a feature, not a timing claim) passes."""
    bounded = [m.span() for m in rules.BOUNDED_SET_RE.finditer(text)]
    tokens = _words(text)
    next_after: dict[int, str] = {}
    for i, (_, _, w_end) in enumerate(tokens):
        next_after[w_end] = tokens[i + 1][0].lower() if i + 1 < len(tokens) else ""
    findings: list[Finding] = []
    strong_spans = [(start, end) for start, end, _ in _find_phrases(text, rules.ABSOLUTE_STRONG)]
    for strong in (True, False):
        vocab = rules.ABSOLUTE_STRONG if strong else rules.ABSOLUTE_WEAK
        for start, end, matched in _find_phrases(text, vocab):
            if any(b_start <= start and end <= b_end for b_start, b_end in bounded):
                continue
            if not strong and any(s <= start and end <= e for s, e in strong_spans):
                continue  # `all` inside `under all circumstances` etc.
            lowered = matched.lower()
            following = next_after.get(end, "")
            if lowered == "every" and following in _TIME_UNITS:
                continue
            if lowered == "instant" and following in {"message", "messages", "messaging"}:
                continue
            findings.append(
                _make_finding(
                    ABSOLUTE_LANGUAGE,
                    "medium" if strong else "low",
                    text,
                    start,
                    end,
                    f'"{matched}" states an absolute that often needs an explicit '
                    "boundary or measurable condition.",
                    "Define the exact boundary, scope, or measurable condition "
                    "this absolute claim is held to.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 9. passive-actor (MEDIUM)
# ---------------------------------------------------------------------------

_PASSIVE_RE = re.compile(
    r"\b(?:" + "|".join(rules.BE_VERBS) + r")\b"
    r"(?:\s+[A-Za-z]+ly\b)?"
    r"\s+(?:[A-Za-z]+(?:ed|en)\b|" + "|".join(sorted(rules.IRREGULAR_PARTICIPLES)) + r"\b)",
    re.IGNORECASE,
)


def detect_passive_actor(text: str) -> list[Finding]:
    """be-verb + participle with no `by <actor>` nearby (`the account shall be
    created …` — by whom?). Copular adjectives (`is required`) and explicit
    `by`-phrases pass; adverbs between verb and participle are included."""
    findings: list[Finding] = []
    for s_start, _, sentence in _sentences(text):
        tokens = _words(sentence)
        for match in _PASSIVE_RE.finditer(sentence):
            words = match.group(0).split()
            participle = words[-1].lower()
            if participle in rules.COPULAR_ADJECTIVES:
                continue
            after = [t for t in tokens if t[1] >= match.end()][:5]
            by_index = next((i for i, t in enumerate(after) if t[0].lower() == "by"), None)
            if by_index is not None and by_index + 1 < len(after):
                continue
            start, end = s_start + match.start(), s_start + match.end()
            findings.append(
                _make_finding(
                    PASSIVE_ACTOR,
                    "medium",
                    text,
                    start,
                    end,
                    "This passive construction names no actor — it is unclear "
                    "which component is responsible for the action.",
                    "Name the responsible component or actor explicitly "
                    '(e.g. "… by the server").',
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 10. missing-constraint (HIGH)
# ---------------------------------------------------------------------------

_MODALS_RE = "|".join(rules.DANGLING_MODALS)
_BARE_OBJECT_RE = re.compile(
    r"\b(?:"
    + _MODALS_RE
    + r")\b\s+([A-Za-z]+)\s+("
    + "|".join(sorted(rules.BARE_OBJECTS | rules.VAGUE_OBJECTS))
    + r")\s*[.!?…]?\s*$",
    re.IGNORECASE,
)


def detect_missing_constraint(text: str) -> list[Finding]:
    """Bare "subject modal verb OBJECT." with nothing after the object (`The
    system shall process requests.` / `Users can modify records.`). Only the
    curated verb–object table fires — short requirements with real content
    (`The system shall log out idle users.`) pass untouched."""
    findings: list[Finding] = []
    for s_start, _, sentence in _sentences(text):
        match = _BARE_OBJECT_RE.search(sentence)
        if not match:
            continue
        verb_span = match.span(1)
        obj_span = match.span(2)
        start, end = s_start + verb_span[0], s_start + obj_span[1]
        modal = sentence[: verb_span[0]].strip().split()[-1].lower()
        reason = (
            "This requirement names an action but none of its conditions, "
            "types, or expected behavior."
        )
        if modal in {"can", "may"}:
            reason += " State which actors hold this permission."
        findings.append(
            _make_finding(
                MISSING_CONSTRAINT,
                "high",
                text,
                start,
                end,
                reason,
                "Specify what kinds, under what conditions, and what the "
                "observable result must be.",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 11. incomplete-requirement (CRITICAL dangling modal / placeholder, HIGH fragment)
# ---------------------------------------------------------------------------

_DANGLING_MODAL_RE = re.compile(r"\b(?:" + _MODALS_RE + r")\b\s*(\.\.\.|…)?\s*$", re.IGNORECASE)
_TRAILING_PREP_RE = re.compile(
    r"\b(?:" + "|".join(sorted(rules.TRAILING_PREPOSITIONS)) + r")\b\s*(\.\.\.|…)?\s*$",
    re.IGNORECASE,
)
_VERBISH = (
    frozenset(rules.DANGLING_MODALS) | frozenset(rules.BE_VERBS) | rules.VERBISH_AFTER_DEMONSTRATIVE
)
_IMPERATIVE_VERBS = frozenset(
    {
        "support",
        "provide",
        "allow",
        "enable",
        "ensure",
        "display",
        "show",
        "send",
        "receive",
        "store",
        "validate",
        "verify",
        "encrypt",
        "decrypt",
        "log",
        "export",
        "import",
        "handle",
        "manage",
        "create",
        "delete",
        "update",
        "process",
        "accept",
        "reject",
        "return",
        "include",
        "require",
        "use",
        "generate",
        "calculate",
        "sync",
        "synchronize",
        "backup",
        "restore",
        "monitor",
        "notify",
        "authenticate",
        "authorize",
    }
)


def detect_incomplete_requirement(text: str) -> list[Finding]:
    """Structural incompleteness: dangling modals (`The system shall…`),
    uppercase placeholders (`TBD`), trailing prepositions (`Support auth
    for…`), trailing colons, and short verbless fragments without data.
    Complete short requirements (imperatives, modals, numbers) pass."""
    stripped = text.strip()
    if not stripped:
        return []
    findings: list[Finding] = []
    offset = text.index(stripped[0])

    for start, end, matched in _find_phrases(text, rules.PLACEHOLDER_TOKENS, case_sensitive=True):
        findings.append(
            _make_finding(
                INCOMPLETE_REQUIREMENT,
                "critical",
                text,
                start,
                end,
                f'The placeholder "{matched}" means this requirement is unfinished.',
                f'Replace "{matched}" with the decided content, or remove the '
                "requirement until it is known.",
            )
        )

    dangling = _DANGLING_MODAL_RE.search(stripped)
    if dangling:
        start, end = offset + dangling.start(), offset + dangling.end()
        findings.append(
            _make_finding(
                INCOMPLETE_REQUIREMENT,
                "critical",
                text,
                start,
                end,
                "The requirement ends on a modal verb with no action — the "
                "sentence is unfinished.",
                "Complete the sentence with the required action and object.",
            )
        )
        return findings  # one structural verdict per requirement suffices here

    trailing = _TRAILING_PREP_RE.search(stripped)
    if trailing:
        start, end = offset + trailing.start(), offset + trailing.end()
        findings.append(
            _make_finding(
                INCOMPLETE_REQUIREMENT,
                "high",
                text,
                start,
                end,
                "The requirement ends on a preposition — the clause it " "introduces is missing.",
                "Complete the trailing clause with its object and conditions.",
            )
        )
        return findings

    if stripped.endswith(":"):
        tokens = _words(stripped)
        context = tokens[-5:] if len(tokens) > 5 else tokens
        start = offset + (context[0][1] if context else len(stripped) - 1)
        findings.append(
            _make_finding(
                INCOMPLETE_REQUIREMENT,
                "high",
                text,
                start,
                offset + len(stripped),
                "The requirement ends on a colon with nothing following it.",
                "Add the listed content the colon promises, or rephrase as a " "complete sentence.",
            )
        )
        return findings

    tokens = _words(stripped)
    lowered = [t[0].lower() for t in tokens]
    has_verb = any(t in _VERBISH for t in lowered) or (
        bool(lowered) and lowered[0] in _IMPERATIVE_VERBS
    )
    has_data = any(ch.isdigit() for ch in stripped)
    if not has_verb and not has_data and len(tokens) < 8:
        findings.append(
            _make_finding(
                INCOMPLETE_REQUIREMENT,
                "high",
                text,
                offset,
                offset + len(stripped),
                "This reads as a verbless fragment rather than a complete " "requirement.",
                "Rephrase as a complete sentence with an actor, a modal verb, "
                "and the required behavior.",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Registry (fixed order — also the dedup tie-break)
# ---------------------------------------------------------------------------

DetectorFn = Callable[[str], list[Finding]]

REGISTRY: tuple[tuple[tuple[str, str], DetectorFn], ...] = (
    (INCOMPLETE_REQUIREMENT, detect_incomplete_requirement),
    (MISSING_CONSTRAINT, detect_missing_constraint),
    (MISSING_MEASURABLE, detect_missing_measurable),
    (AMBIGUOUS_OPERATOR, detect_ambiguous_operator),
    (VAGUE_QUANTIFIER, detect_vague_quantifier),
    (SUBJECTIVE_TERM, detect_subjective_term),
    (UNDEFINED_TERM, detect_undefined_terminology),
    (PASSIVE_ACTOR, detect_passive_actor),
    (PRONOUN_REFERENCE, detect_pronoun_reference),
    (ABSOLUTE_LANGUAGE, detect_absolute_language),
    (OPTIONAL_LANGUAGE, detect_optional_language),
)
