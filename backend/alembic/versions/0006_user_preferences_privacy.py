"""User privacy preferences (Stage 23).

Revision ID: 0006
Revises: 0005

Adds `user_preferences` for enforced privacy lifecycle settings. The first
preference is `history_retention_days`: NULL means no automatic retention rule;
1..3650 days is enforced by both schema and application validation. Account
deletion cascades preferences with the owning user.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("history_retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "history_retention_days IS NULL OR "
            "(history_retention_days >= 1 AND history_retention_days <= 3650)",
            name="ck_user_preferences_history_retention_days",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
