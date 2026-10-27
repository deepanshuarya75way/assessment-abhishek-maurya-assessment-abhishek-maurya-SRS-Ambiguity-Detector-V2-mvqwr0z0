"""Email port: message value, shared templates, service ABC.

Adapters (`resend.py`, `console.py`) render via :func:`render_email` so every
template has ONE subject/body definition. Template context may carry tokens and
links — adapters must NEVER log them (log to/template/subject only).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

TEMPLATE_RESET_PASSWORD = "reset_password"  # noqa: S105 — template id, not a credential
TEMPLATE_SECURITY_NOTICE = "security_notice"
TEMPLATE_ACCOUNT_EXISTS = "account_exists"


@dataclass(frozen=True)
class EmailMessage:
    """One outbound email. `context` holds template vars (may include tokens)."""

    to: str
    template: str
    context: dict[str, str] = field(default_factory=dict)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def render_email(message: EmailMessage, app_base_url: str) -> tuple[str, str]:
    """Render (subject, html body) for a message. Unknown template → ValueError
    (programmer error, never user input). All interpolated vars are escaped."""
    base = app_base_url.rstrip("/")
    ctx = message.context
    if message.template == TEMPLATE_RESET_PASSWORD:
        subject = "Reset your password — SRS Ambiguity Detector"
        link = f"{base}/reset-password?token={ctx['token']}"
        body = (
            "<p>Someone requested a password reset for this email address.</p>"
            f'<p><a href="{_escape(link)}">Reset password</a></p>'
            f"<p>This link expires in {_escape(ctx.get('expiry_minutes', '60'))} minutes "
            "and can be used once. If that wasn't you, you can ignore this email — "
            "your password stays unchanged.</p>"
        )
    elif message.template == TEMPLATE_SECURITY_NOTICE:
        subject = f"Security notice — {_escape(ctx.get('title', 'your account'))}"
        body = (
            f"<p>{_escape(ctx.get('detail', 'A security-relevant change was made.'))}</p>"
            "<p>If that wasn't you, reset your password immediately and contact support.</p>"
        )
    elif message.template == TEMPLATE_ACCOUNT_EXISTS:
        subject = "You already have an account — SRS Ambiguity Detector"
        body = (
            "<p>Someone tried to register with this email address, which already has "
            "an account. If that was you, you can log in directly"
            f' at <a href="{_escape(base)}/login">{_escape(base)}/login</a>'
            " (or reset your password if you forgot it). If it wasn't you, no action "
            "is needed — your account is unchanged.</p>"
        )
    else:
        raise ValueError(f"Unknown email template: {message.template!r}")
    return subject, f"<html><body>{body}</body></html>"


class EmailService(ABC):
    """Transactional-email port. `send` is best-effort BY CONTRACT: adapters MUST
    catch transport errors, log safely (never token/link/body), and NOT raise —
    callers schedule sends as post-commit background work
    as the recovery path (ARCHITECTURE auth flows)."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        """Deliver one message (best-effort; never raises, never logs secrets)."""
