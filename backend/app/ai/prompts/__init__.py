"""Versioned, provider-independent generation prompts (AI_PROVIDER_SPEC §2–§3).

One module per prompt version (`overview_v1`, `improvement_v1`, ...): the
SYSTEM string is the stable instruction, `render_*` formats a validated
payload into the user message. Adapters pass both through UNCHANGED apart
from transport shaping (chat messages vs `generateContent` parts) — prompt
wording is identical on every provider, so generations stay comparable and
prompt fixes ship in ONE place.

Injection rule (§3): requirement/finding text is untrusted user data that
may itself contain instructions ("ignore previous..."). Payloads render
inside DELIMITED blocks explicitly framed as data, and every system prompt
orders the model to ignore instructions found inside those blocks. The
overview endpoint never executes tool calls — there is nothing to hijack.
"""

from app.ai.prompts.improvement_v1 import (
    IMPROVEMENT_SYSTEM_PROMPT,
    IMPROVEMENT_VERSION,
    render_improvement,
)
from app.ai.prompts.overview_v1 import (
    OVERVIEW_SYSTEM_PROMPT,
    OVERVIEW_VERSION,
    render_overview,
)

__all__ = [
    "IMPROVEMENT_SYSTEM_PROMPT",
    "IMPROVEMENT_VERSION",
    "OVERVIEW_SYSTEM_PROMPT",
    "OVERVIEW_VERSION",
    "render_improvement",
    "render_overview",
]
