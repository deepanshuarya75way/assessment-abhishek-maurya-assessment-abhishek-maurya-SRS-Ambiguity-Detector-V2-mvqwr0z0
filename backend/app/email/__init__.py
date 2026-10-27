"""Transactional email port + adapters (Resend prod, console/file dev).

The router wires the factory result into `app.state.email_service` at startup;
tests override it with an in-memory fake (never real sends in tests).
"""

from app.core.config import get_settings
from app.email.base import (
    TEMPLATE_ACCOUNT_EXISTS,
    TEMPLATE_RESET_PASSWORD,
    TEMPLATE_SECURITY_NOTICE,
    EmailMessage,
    EmailService,
    render_email,
)
from app.email.console import ConsoleEmailService
from app.email.resend import ResendEmailService

__all__ = [
    "ConsoleEmailService",
    "EmailMessage",
    "EmailService",
    "ResendEmailService",
    "TEMPLATE_ACCOUNT_EXISTS",
    "TEMPLATE_RESET_PASSWORD",
    "TEMPLATE_SECURITY_NOTICE",
    "get_email_service",
    "render_email",
]


def get_email_service() -> EmailService:
    """Build the configured adapter. Console is REFUSED in production and Resend
    requires its key (both fail closed — never silently undelivered in prod)."""
    settings = get_settings()
    if settings.EMAIL_PROVIDER == "console":
        if settings.is_production:
            raise RuntimeError(
                "EMAIL_PROVIDER=console is forbidden in production "
                "(set EMAIL_PROVIDER=resend with RESEND_API_KEY)."
            )
        return ConsoleEmailService(settings.DEV_OUTBOX_DIR, settings.APP_BASE_URL)
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured (see backend/.env.example).")
    return ResendEmailService(settings.RESEND_API_KEY, settings.EMAIL_FROM, settings.APP_BASE_URL)
