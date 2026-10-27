"""Remove email-confirmation flow and unlock existing accounts.

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET is_verified = true WHERE is_verified = false"))
    op.drop_table("email_verification_tokens")

def downgrade() -> None:
    # Restoring the token table cannot restore confirmation requirements or tokens.
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_verification_tokens_owner", "email_verification_tokens", ["owner_id"])
