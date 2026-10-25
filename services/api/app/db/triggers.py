"""Database triggers and anti-tamper security enforcement."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

logger = logging.getLogger("ps05.db.triggers")

# PostgreSQL Trigger Definitions
PG_PREVENT_AUDIT_TAMPERING_FN = """
CREATE OR REPLACE FUNCTION prevent_audit_tampering()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be updated or deleted.';
END;
$$ LANGUAGE plpgsql;
"""

PG_AUDIT_TAMPERING_TRIGGER = """
DROP TRIGGER IF EXISTS trg_prevent_audit_tampering ON audit_events;
CREATE TRIGGER trg_prevent_audit_tampering
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_tampering();
"""

PG_PREVENT_EVIDENCE_HASH_MODIFICATION_FN = """
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
"""

PG_EVIDENCE_HASH_TRIGGER = """
DROP TRIGGER IF EXISTS trg_prevent_evidence_hash_modification ON evidence_items;
CREATE TRIGGER trg_prevent_evidence_hash_modification
BEFORE UPDATE ON evidence_items
FOR EACH ROW
EXECUTE FUNCTION prevent_evidence_hash_modification();
"""

# SQLite Trigger Definitions
SQLITE_AUDIT_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(
        ABORT,
        'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be updated.'
    );
END;
"""

SQLITE_AUDIT_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(
        ABORT,
        'CRITICAL SECURITY VIOLATION: Audit logs are physically immutable and cannot be deleted.'
    );
END;
"""

SQLITE_EVIDENCE_HASH_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_prevent_evidence_hash_modification
BEFORE UPDATE OF primary_hash_sha256 ON evidence_items
WHEN OLD.primary_hash_sha256 IS NOT NEW.primary_hash_sha256
BEGIN
    SELECT RAISE(
        ABORT,
        'CRITICAL SECURITY VIOLATION: Primary hash cannot be modified once ingested.'
    );
END;
"""


async def install_security_triggers(target: AsyncConnection | AsyncSession) -> None:
    """Install anti-tamper triggers on the target connection or session according to dialect."""
    if isinstance(target, AsyncSession):
        conn = await target.connection()
    else:
        conn = target

    dialect_name = conn.dialect.name
    if dialect_name == "postgresql":
        await conn.execute(text(PG_PREVENT_AUDIT_TAMPERING_FN))
        await conn.execute(text(PG_AUDIT_TAMPERING_TRIGGER))
        await conn.execute(text(PG_PREVENT_EVIDENCE_HASH_MODIFICATION_FN))
        await conn.execute(text(PG_EVIDENCE_HASH_TRIGGER))
        logger.info("Installed PostgreSQL anti-tampering PL/pgSQL triggers.")
    elif dialect_name == "sqlite":
        await conn.execute(text(SQLITE_AUDIT_UPDATE_TRIGGER))
        await conn.execute(text(SQLITE_AUDIT_DELETE_TRIGGER))
        await conn.execute(text(SQLITE_EVIDENCE_HASH_TRIGGER))
        logger.info("Installed SQLite anti-tampering triggers.")
    else:
        logger.warning("No native security triggers configured for dialect: %s", dialect_name)
