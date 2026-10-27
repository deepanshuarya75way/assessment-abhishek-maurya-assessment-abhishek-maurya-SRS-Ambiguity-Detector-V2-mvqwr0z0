"""Console + file-outbox adapter (LOCAL DEV ONLY — refused in production).

Logs metadata (to/template/subject) WITHOUT tokens or links, and writes the full
rendered mail (including the clickable link) to DEV_OUTBOX_DIR so the password-reset
flows are manually testable without a provider. The outbox dir is git-ignored;
production use raises at factory time (fail closed).
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger
from app.email.base import EmailMessage, EmailService, render_email

logger = get_logger(__name__)


class ConsoleEmailService(EmailService):
    """Dev adapter: loud metadata log + full mail to a local outbox file."""

    def __init__(self, outbox_dir: str, app_base_url: str) -> None:
        self._outbox_dir = Path(outbox_dir)
        self._app_base_url = app_base_url

    async def send(self, message: EmailMessage) -> None:
        subject, html = render_email(message, self._app_base_url)
        logger.info(
            "DEV-ONLY email (NOT delivered): template=%s subject=%s",
            message.template,
            subject,
            extra={"email_provider": "console", "email_template": message.template},
        )
        try:
            self._outbox_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            path = self._outbox_dir / f"{stamp}-{message.template}-{uuid.uuid4().hex[:8]}.html"
            path.write_text(f"<!-- To: {message.to} -->\n{html}", encoding="utf-8")
        except OSError:
            logger.exception(
                "Dev outbox write failed (dir=%s)",
                self._outbox_dir,
                extra={"email_provider": "console", "email_template": message.template},
            )
