"""Document detected file type (Stage 08).

Revision ID: 0005
Revises: 0004

Adds `documents.file_type` — the SERVER-verified type (pdf/docx/txt), distinct
from the extension (user claim) and the stored MIME (canonical per type). NULL
is allowed: rows predating Stage 08 (none exist in practice — uploads did not)
have no verified type, and NULL says so honestly instead of backfilling a lie.
New code always sets it. Downgrade drops the column + CHECK (metadata-only;
binaries in object storage are untouched).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("file_type", sa.String(8), nullable=True))
    op.create_check_constraint(
        "ck_documents_file_type", "documents", "file_type IN ('pdf', 'docx', 'txt')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_file_type", "documents", type_="check")
    op.drop_column("documents", "file_type")
