"""Detector vocabularies + compiled patterns (Stage 07).

Single home for every tunable the detectors match against: word lists live
here as documented frozensets, never scattered through route handlers or
detector bodies. Detectors (`detectors.py`) add the contextual guards; the
engine (`engine.py`) adds dedup + scoring. To tune a detector, edit data here
and add/adjust its tests — never rewrite the engine.

Matching conventions (all detectors): case-insensitive unless noted, real word
boundaries (`\\b` — no substring accidents like "some" in "someone"), matches
reported with requirement-relative `[start, end)` offsets.
"""

import re

# ---------------------------------------------------------------------------
# vague-quantifier (MEDIUM)
# ---------------------------------------------------------------------------
# Bare quantity words with no explicit amount. Guarded in the detector: the
# bounded frame "as <q> as <n>" ("as many as 5") does NOT fire.
VAGUE_QUANTIFIERS: tuple[str, ...] = (
    "some",
    "many",
    "few",
    "several",
    "various",
    "numerous",
    "a number of",
    "a lot of",
)

# ---------------------------------------------------------------------------
# subjective-term (MEDIUM)
# ---------------------------------------------------------------------------
# Quality words with no intrinsic measurable definition. Single words fire
# standalone; multiword entries fire as phrases. Guarded: an explicit external
# definition ("as defined in …", "as specified in …") in the same sentence
# suppresses the finding (the requirement points at its own criterion).
SUBJECTIVE_TERMS: tuple[str, ...] = (
    "easy",
    "easily",
    "fast",
    "quick",
    "quickly",
    "efficient",
    "efficiently",
    "user-friendly",
    "user friendly",
    "simple",
    "simply",
    "secure",
    "securely",
    "robust",
    "reliable",
    "reliably",
    "appropriate",
    "suitable",
    "convenient",
    "conveniently",
    "seamless",
    "seamlessly",
    "intuitive",
    "intuitively",
    "modern",
    "high performance",
    "high-performance",
    "responsive",
    "responsively",
)
# "… as defined in the style guide" — the term is anchored elsewhere.
EXTERNAL_DEFINITION_RE = re.compile(r"\bas\s+(defined|specified)\s+in\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# missing-measurable-criteria (HIGH)
# ---------------------------------------------------------------------------
# A quality CLAIM (signal + up to two preceding words, e.g. "respond quickly",
# "be highly available") with no numeric threshold in the same sentence.
# Numbers may be digits ("2", "99.9") or words ("two"); a bare number is not
# enough — it must carry a measurement unit (time, percent, size, rate, count).
MEASURABLE_SIGNALS: tuple[str, ...] = (
    "quick",
    "quickly",
    "fast",
    "slow",
    "slowly",
    "efficient",
    "efficiently",
    "scalable",
    "scalability",
    "reliable",
    "reliability",
    "available",
    "availability",
    "performant",
    "performance",
    "responsive",
    "responsiveness",
    "timely",
    "promptly",
    "soon",
    "response time",
    "throughput",
    "latency",
    "uptime",
    "error rate",
    "processing time",
    "memory",
    "capacity",
    "load",
)
_THRESHOLD_UNITS: tuple[str, ...] = (
    "second",
    "seconds",
    "ms",
    "millisecond",
    "milliseconds",
    "minute",
    "minutes",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "year",
    "years",
    "percent",
    "percentage",
    "%",
    "byte",
    "bytes",
    "kb",
    "mb",
    "gb",
    "tb",
    "request",
    "requests",
    "req",
    "transaction",
    "transactions",
    "tps",
    "concurrent",
    "user",
    "users",
    "record",
    "records",
    "item",
    "items",
)
_WORD_NUMBERS: tuple[str, ...] = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "million",
    "billion",
)
_WORD_UNITS: tuple[str, ...] = tuple(u for u in _THRESHOLD_UNITS if u != "%")
# "%" needs a lookahead (it is a non-word char, so `\b` never follows it).
THRESHOLD_RE = re.compile(
    r"(?:\d+(?:\.\d+)?|\b(?:" + "|".join(_WORD_NUMBERS) + r")\b)"
    r"\s*(?:%(?=\s|$|[.,;:!?])|(?:" + "|".join(_WORD_UNITS) + r")\b)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# optional-language (LOW)
# ---------------------------------------------------------------------------
# Modals + hedges that leave commitment unclear. `shall`/`must`/`will` are
# commitment language and NEVER fire here; `can` reads as permission, not
# uncertainty, and is deliberately absent (see missing-constraint instead).
OPTIONAL_MODALS: tuple[str, ...] = ("may", "might", "could", "should")
OPTIONAL_HEDGES: tuple[str, ...] = (
    "possibly",
    "if possible",
    "as needed",
    "where appropriate",
    "when necessary",
)

# ---------------------------------------------------------------------------
# pronoun-reference (MEDIUM `it`/`they` group, LOW bare demonstratives)
# ---------------------------------------------------------------------------
# Heuristic antecedent check: domain + capitalized nouns preceding the pronoun
# are counted as candidates; firing rules live in the detector.
PRONOUNS_IT: tuple[str, ...] = ("it", "its")
PRONOUNS_THEY: tuple[str, ...] = ("they", "them", "their")
PRONOUNS_GENDERED: tuple[str, ...] = ("he", "she")
PRONOUNS_DEMONSTRATIVE: tuple[str, ...] = ("this", "that", "these", "those")
# Human-ish nouns: exactly one lets singular/plural "they" pass (brief §10:
# "The user logs in. They receive …" is acceptable).
HUMAN_NOUNS: frozenset[str] = frozenset(
    {
        "user",
        "users",
        "admin",
        "admins",
        "administrator",
        "administrators",
        "customer",
        "customers",
        "operator",
        "operators",
        "member",
        "members",
        "manager",
        "managers",
        "developer",
        "developers",
        "tester",
        "testers",
        "auditor",
        "auditors",
        "guest",
        "guests",
    }
)
# Domain nouns that count as referent candidates alongside capitalized words.
DOMAIN_NOUNS: frozenset[str] = frozenset(
    {
        "system",
        "systems",
        "server",
        "servers",
        "client",
        "clients",
        "application",
        "applications",
        "app",
        "apps",
        "service",
        "services",
        "database",
        "databases",
        "data",
        "account",
        "accounts",
        "request",
        "requests",
        "response",
        "responses",
        "result",
        "results",
        "file",
        "files",
        "record",
        "records",
        "session",
        "sessions",
        "message",
        "messages",
        "email",
        "emails",
        "profile",
        "profiles",
        "order",
        "orders",
        "payment",
        "payments",
        "report",
        "reports",
        "form",
        "forms",
        "page",
        "pages",
        "password",
        "passwords",
        "token",
        "tokens",
        "key",
        "keys",
        "log",
        "logs",
        "cache",
        "queue",
        "queues",
        "job",
        "jobs",
        "task",
        "tasks",
        "module",
        "modules",
        "component",
        "components",
        "interface",
        "interfaces",
        "api",
        "apis",
        "endpoint",
        "endpoints",
    }
)
# A demonstrative followed by one of these (or punctuation/end) stands alone
# ("This is required") rather than modifying a noun ("this report").
VERBISH_AFTER_DEMONSTRATIVE: frozenset[str] = frozenset(
    {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
    }
)

# ---------------------------------------------------------------------------
# ambiguous-operator (HIGH `and/or`/`etc.`/`and so on`, LOW bare `or`/`as well as`)
# ---------------------------------------------------------------------------
MULTIWORD_OPERATORS: tuple[tuple[str, str], ...] = (
    ("and/or", "high"),
    ("etc.", "high"),
    ("etc", "high"),
    ("and so on", "high"),
    ("as well as", "low"),
)
# Explicit alternation markers: bare "or" beside these does NOT fire.
EXPLICIT_ALTERNATION_RE = re.compile(r"\b(either|whether)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# undefined-terminology (LOW)
# ---------------------------------------------------------------------------
# Qualifiers that modify a following word ("standard security", "normal load").
# Bare nouns ("comply with the standard") do NOT fire — the qualifier must
# attach to something to be questioned.
UNDEFINED_QUALIFIERS: tuple[str, ...] = (
    "enterprise-grade",
    "standard",
    "normal",
    "appropriate",
    "suitable",
    "approved",
    "authorized",
    "relevant",
    "adequate",
    "sufficient",
    "reasonable",
    "usual",
    "typical",
    "supported",
    "business",
)

# ---------------------------------------------------------------------------
# absolute-language (MEDIUM strong absolutes, LOW `any`/`all`)
# ---------------------------------------------------------------------------
ABSOLUTE_STRONG: tuple[str, ...] = (
    "always",
    "never",
    "every",
    "none",
    "100%",
    "completely",
    "instant",
    "zero",
    "under all circumstances",
)
ABSOLUTE_WEAK: tuple[str, ...] = ("any", "all")
# Bounded universals ("any of the following", "all listed") are precise.
BOUNDED_SET_RE = re.compile(
    r"\b(any|all|none)\s+of\s+the\s+(following|above|below)\b"
    r"|\b(any|all|none)\s+(listed|above|below|specified)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# passive-actor (MEDIUM)
# ---------------------------------------------------------------------------
# be-verb + participle with no "by <actor>" nearby. Participles: regular
# (-ed/-en) + this irregular list; copular adjectives below are NOT actions.
BE_VERBS: tuple[str, ...] = ("is", "are", "was", "were", "be", "been", "being")
IRREGULAR_PARTICIPLES: frozenset[str] = frozenset(
    {
        "built",
        "sent",
        "shown",
        "written",
        "taken",
        "given",
        "made",
        "done",
        "found",
        "chosen",
        "frozen",
        "hidden",
        "broken",
        "driven",
        "forgotten",
        "mistaken",
        "paid",
        "said",
        "told",
        "sold",
        "held",
        "kept",
        "left",
        "meant",
        "met",
        "spent",
        "lost",
        "known",
        "grown",
        "drawn",
        "thrown",
        "worn",
        "torn",
    }
)
# States, not actions ("Password is required" has no missing actor).
COPULAR_ADJECTIVES: frozenset[str] = frozenset(
    {"required", "used", "unused", "enabled", "disabled", "retired"}
)

# ---------------------------------------------------------------------------
# missing-constraint (HIGH)
# ---------------------------------------------------------------------------
# Bare "subject modal verb OBJECT." with nothing after the object — the
# requirement names an action but none of its conditions, types, or behavior.
# Only verb–object pairs in this table fire (conservative by construction).
BARE_OBJECTS: frozenset[str] = frozenset(
    {
        "requests",
        "data",
        "records",
        "input",
        "output",
        "files",
        "messages",
        "transactions",
        "operations",
        "queries",
        "commands",
        "events",
        "tasks",
        "jobs",
    }
)
VAGUE_OBJECTS: frozenset[str] = frozenset({"things", "stuff"})

# ---------------------------------------------------------------------------
# incomplete-requirement (CRITICAL dangling modal / placeholder, HIGH fragment)
# ---------------------------------------------------------------------------
DANGLING_MODALS: tuple[str, ...] = ("shall", "must", "should", "will", "can", "may")
# Placeholders are matched CASE-SENSITIVELY (uppercase convention — a lowercase
# "todo list" is a feature, not a placeholder).
PLACEHOLDER_TOKENS: tuple[str, ...] = ("TBD", "TBC", "TODO", "FIXME", "XXX")
TRAILING_PREPOSITIONS: frozenset[str] = frozenset(
    {"for", "with", "to", "from", "in", "on", "of", "by", "via", "through", "against"}
)
