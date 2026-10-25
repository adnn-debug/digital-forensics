"""Persist report jurisdiction and examiner context fields.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("examiner_certification", sa.String(length=255), nullable=True))
    op.add_column("reports", sa.Column("jurisdiction", sa.String(length=255), nullable=True))
    op.add_column("reports", sa.Column("court_name", sa.String(length=255), nullable=True))
    op.add_column("reports", sa.Column("docket_number", sa.String(length=128), nullable=True))
    op.add_column("reports", sa.Column("classification_marking", sa.String(length=128), nullable=True))
    op.add_column("reports", sa.Column("verification_token", sa.String(length=64), nullable=True))
    op.create_index("ix_reports_verification_token", "reports", ["verification_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_reports_verification_token", table_name="reports")
    op.drop_column("reports", "verification_token")
    op.drop_column("reports", "classification_marking")
    op.drop_column("reports", "docket_number")
    op.drop_column("reports", "court_name")
    op.drop_column("reports", "jurisdiction")
    op.drop_column("reports", "examiner_certification")
