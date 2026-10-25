"""
Seed script — creates the default investigator account for the PS-05 platform.

Usage (from repo root, venv active):
    python services/api/scripts/seed_investigator.py

The script is idempotent: if the account already exists it prints a notice
and exits cleanly without modifying anything.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure `app` package is importable when run from repo root or scripts dir
# ---------------------------------------------------------------------------
_API_DIR = Path(__file__).resolve().parents[1]  # services/api/
sys.path.insert(0, str(_API_DIR))

# Load .env from repo root if present
_REPO_ROOT = _API_DIR.parents[1]
_env_file = _REPO_ROOT / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Investigator credentials (edit here if you want different values)
# ---------------------------------------------------------------------------
INVESTIGATOR_EMAIL = "c1pher@ps05.local"
INVESTIGATOR_PASSWORD = "6767"          # plain-text; will be bcrypt-hashed
INVESTIGATOR_FULL_NAME = "c1pher"
INVESTIGATOR_ROLE = UserRole.ADMIN      # ADMIN so they can access all routes

# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./storage/ps05_dev.db",
)


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal: sessionmaker[AsyncSession] = sessionmaker(  # type: ignore[type-arg]
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with AsyncSessionLocal() as session:
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.email == INVESTIGATOR_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(
                f"[SEED] Investigator '{INVESTIGATOR_EMAIL}' already exists "
                f"(id={existing.id}). No changes made."
            )
        else:
            hashed = hash_password(INVESTIGATOR_PASSWORD)
            user = User(
                email=INVESTIGATOR_EMAIL,
                full_name=INVESTIGATOR_FULL_NAME,
                hashed_password=hashed,
                role=INVESTIGATOR_ROLE,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(
                f"[SEED] Created investigator account:\n"
                f"       ID       : {user.id}\n"
                f"       Email    : {user.email}\n"
                f"       Name     : {user.full_name}\n"
                f"       Role     : {user.role.value}\n"
                f"       Password : {INVESTIGATOR_PASSWORD}  (bcrypt-hashed in DB)\n"
            )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
