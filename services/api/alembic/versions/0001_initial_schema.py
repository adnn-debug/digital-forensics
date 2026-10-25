"""Initial schema with domain tables and anti-tamper triggers.

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. cases table
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lead_investigator_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_investigator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_index("ix_cases_created_at", "cases", ["created_at"])

    # 3. evidence_items table
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_number", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("primary_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("hash_md5", sa.String(length=32), nullable=False),
        sa.Column("hash_sha1", sa.String(length=40), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("is_quarantined", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_items_primary_hash_sha256", "evidence_items", ["primary_hash_sha256"]
    )
    op.create_index(
        "ix_evidence_items_case_hash", "evidence_items", ["case_id", "primary_hash_sha256"]
    )
    op.create_index("ix_evidence_items_media_type", "evidence_items", ["media_type"])

    # 4. hash_verifications table
    op.create_table(
        "hash_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("calculated_sha256", sa.String(length=64), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_intact", sa.Boolean(), nullable=False),
        sa.Column("verification_trigger", sa.String(length=64), nullable=False),
        sa.Column("verified_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hash_verifications_intact", "hash_verifications", ["is_intact"])
    op.create_index("ix_hash_verifications_verified_at", "hash_verifications", ["verified_at"])

    # 5. metadata_extracts table
    op.create_table(
        "metadata_extracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=False),
        sa.Column("raw_metadata", json_type, nullable=False),
        sa.Column("filtered_forensic_metadata", json_type, nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metadata_extracts_tool", "metadata_extracts", ["tool_name"])

    # 6. forensic_analyses table
    op.create_table(
        "forensic_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters", json_type, nullable=True),
        sa.Column("summary_results", json_type, nullable=True),
        sa.Column("examiner_notes", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forensic_analyses_status", "forensic_analyses", ["status"])
    op.create_index("ix_forensic_analyses_type", "forensic_analyses", ["analysis_type"])

    # 7. findings table
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("evidence_offset", sa.String(length=64), nullable=True),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["forensic_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_type", "findings", ["finding_type"])
    op.create_index("ix_findings_created_at", "findings", ["created_at"])

    # 8. analysis_artifacts table
    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["forensic_analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_artifacts_type", "analysis_artifacts", ["artifact_type"])
    op.create_index("ix_analysis_artifacts_hash", "analysis_artifacts", ["hash_sha256"])

    # 8. audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("previous_state_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_delta", json_type, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"])

    # 9. reports table
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("report_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("generated_by_id", sa.Uuid(), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("included_evidence_ids", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_report_number", "reports", ["report_number"], unique=True)
    op.create_index("ix_reports_file_hash_sha256", "reports", ["file_hash_sha256"])
    op.create_index("ix_reports_created_at", "reports", ["created_at"])

    # 10. Install Security Triggers (Dialect-dependent)
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        # Audit immutability trigger
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_audit_tampering()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION
                    'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be updated or deleted.';
            END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER trg_prevent_audit_tampering
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW
            EXECUTE FUNCTION prevent_audit_tampering();
        """)
        # Evidence primary hash modification trigger
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_evidence_hash_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.primary_hash_sha256 IS DISTINCT FROM NEW.primary_hash_sha256 THEN
                    RAISE EXCEPTION
                        'CRITICAL SECURITY VIOLATION: Primary hash cannot be modified once ingested.';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER trg_prevent_evidence_hash_modification
            BEFORE UPDATE ON evidence_items
            FOR EACH ROW
            EXECUTE FUNCTION prevent_evidence_hash_modification();
        """)
    elif dialect_name == "sqlite":
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be updated.'
                );
            END;
        """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be deleted.'
                );
            END;
        """)
        op.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_prevent_evidence_hash_modification
            BEFORE UPDATE OF primary_hash_sha256 ON evidence_items
            WHEN OLD.primary_hash_sha256 IS NOT NEW.primary_hash_sha256
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'CRITICAL SECURITY VIOLATION: Primary hash cannot be modified once ingested.'
                );
            END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_tampering ON audit_events;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_tampering();")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_prevent_evidence_hash_modification ON evidence_items;"
        )
        op.execute("DROP FUNCTION IF EXISTS prevent_evidence_hash_modification();")
    elif dialect_name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_update;")
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_delete;")
        op.execute("DROP TRIGGER IF EXISTS trg_prevent_evidence_hash_modification;")

    op.drop_table("reports")
    op.drop_table("audit_events")
    op.drop_table("analysis_artifacts")
    op.drop_table("findings")
    op.drop_table("forensic_analyses")
    op.drop_table("metadata_extracts")
    op.drop_table("hash_verifications")
    op.drop_table("evidence_items")
    op.drop_table("cases")
    op.drop_table("users")
