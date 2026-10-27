"""Resend adapter (production email). HTTP via httpx; best-effort per the port."""

import httpx

from app.core.logging import get_logger
from app.email.base import EmailMessage, EmailService, render_email

logger = get_logger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_REQUEST_TIMEOUT_S = 10.0


class ResendEmailService(EmailService):
    """Delivers via the Resend HTTP API. Transport failures are logged (recipient
    + template only — never token/link/body) and swallowed (port contract)."""

    def __init__(self, api_key: str, sender: str, app_base_url: str) -> None:
        self._api_key = api_key
        self._sender = sender
        self._app_base_url = app_base_url

    async def send(self, message: EmailMessage) -> None:
        try:
            subject, html = render_email(message, self._app_base_url)
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                response = await client.post(
                    _RESEND_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "from": self._sender,
                        "to": [message.to],
                        "subject": subject,
                        "html": html,
                    },
                )
            if response.status_code >= 300:
                logger.error(
                    "Resend delivery failed (status=%s template=%s)",
                    response.status_code,
                    message.template,
                    extra={
                        "email_provider": "resend",
                        "email_template": message.template,
                        "status_code": response.status_code,
                    },
                )
        except Exception:
            # Swallowed by port contract: auth flows already committed; the resend
            # endpoints are the recovery path. Log carries no token/link/body.
            logger.exception(
                "Resend delivery error (template=%s)",
                message.template,
                extra={"email_provider": "resend", "email_template": message.template},
            )
