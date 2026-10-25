"""Durable background jobs tracking columns and indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add durable background job columns to forensic_analyses table
    op.add_column("forensic_analyses", sa.Column("job_id", sa.String(length=128), nullable=True))
    op.add_column(
        "forensic_analyses",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "forensic_analyses",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "forensic_analyses",
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "forensic_analyses",
        sa.Column("timeout_seconds", sa.Integer(), server_default="300", nullable=False),
    )
    op.add_column("forensic_analyses", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column(
        "forensic_analyses",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "forensic_analyses",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "forensic_analyses",
        sa.Column("worker_id", sa.String(length=128), nullable=True),
    )

    op.create_index("ix_forensic_analyses_job_id", "forensic_analyses", ["job_id"])
    op.create_index("ix_forensic_analyses_idempotency", "forensic_analyses", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_forensic_analyses_idempotency", table_name="forensic_analyses")
    op.drop_index("ix_forensic_analyses_job_id", table_name="forensic_analyses")
    op.drop_column("forensic_analyses", "worker_id")
    op.drop_column("forensic_analyses", "last_heartbeat_at")
    op.drop_column("forensic_analyses", "started_at")
    op.drop_column("forensic_analyses", "error_code")
    op.drop_column("forensic_analyses", "timeout_seconds")
    op.drop_column("forensic_analyses", "max_retries")
    op.drop_column("forensic_analyses", "attempt_count")
    op.drop_column("forensic_analyses", "idempotency_key")
    op.drop_column("forensic_analyses", "job_id")
