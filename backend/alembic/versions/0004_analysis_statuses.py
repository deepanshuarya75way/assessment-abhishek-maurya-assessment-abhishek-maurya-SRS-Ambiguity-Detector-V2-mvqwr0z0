"""Analysis pipeline statuses: `analyzed` (+ reserved `failed`) (Stage 07).

Revision ID: 0004
Revises: 0003

Hand-written (a CHECK replacement — autogenerate cannot express it). Stage 07
persists `analyzed` rows (scored, with issues); `failed` is reserved for a
future async/retry flow — the synchronous POST rolls back fully on error and
never writes it (a 500 with no partial state, strictly safer than a FAILED
row). `segmented` stays valid for pre-Stage-07 rows. No data migration: every
existing row already satisfies the widened CHECK.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CHECK = "status IN ('segmented')"
_NEW_CHECK = "status IN ('segmented', 'analyzed', 'failed')"


def upgrade() -> None:
    op.drop_constraint("ck_analyses_status", "analyses", type_="check")
    op.create_check_constraint("ck_analyses_status", "analyses", _NEW_CHECK)


def downgrade() -> None:
    # Analyzed rows cannot satisfy the restored single-value CHECK.
    op.execute("DELETE FROM analyses WHERE status <> 'segmented'")
    op.drop_constraint("ck_analyses_status", "analyses", type_="check")
    op.create_check_constraint("ck_analyses_status", "analyses", _OLD_CHECK)
