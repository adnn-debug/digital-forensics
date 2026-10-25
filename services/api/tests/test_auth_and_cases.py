"""
Integration tests for authentication and case management.

Tests:
- Unauthorized access to protected routes
- Invalid credentials
- Authorized case access (own case)
- Attempt to access another user's case (403)
- Case CRUD happy path
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.case import Case, CaseStatus
from app.db.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


async def _create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str = "Secure1234!",
    role: UserRole = UserRole.EXAMINER,
) -> User:
    """Persist a test user directly to the in-memory DB."""
    from uuid import uuid4

    user = User(
        id=uuid4(),
        email=email.lower(),
        hashed_password=hash_password(password),
        full_name="Test User",
        role=role.value,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_case(
    db: AsyncSession,
    *,
    case_number: str,
    lead_id: object,
) -> Case:
    """Persist a test case directly."""
    from uuid import uuid4

    case = Case(
        id=uuid4(),
        case_number=case_number.upper(),
        title=f"Test Case {case_number}",
        status=CaseStatus.ACTIVE.value,
        lead_investigator_id=lead_id,
    )
    db.add(case)
    await db.flush()
    return case


async def _login(client: AsyncClient, email: str, password: str = "Secure1234!") -> str:
    """Return a valid Bearer token for the given credentials."""
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    """Return Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: Unauthorized access to protected routes
# ---------------------------------------------------------------------------


class TestUnauthorizedAccess:
    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, async_client: AsyncClient) -> None:
        """GET /cases without a token must return 401."""
        resp = await async_client.get("/api/v1/cases")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(self, async_client: AsyncClient) -> None:
        """A garbage Bearer value must be rejected with 401."""
        resp = await async_client.get(
            "/api/v1/cases",
            headers={"Authorization": "Bearer this.is.not.a.jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_on_me_returns_401(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_create_case_returns_401(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/cases",
            json={"case_number": "CAS-2026-0099", "title": "Unauthorized"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: Invalid credentials
# ---------------------------------------------------------------------------


class TestInvalidCredentials:
    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        await _create_user(test_db_session, email="alice@test.com")
        await test_db_session.commit()

        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "alice@test.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["detail"]["code"] == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_unknown_email_returns_401(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@test.com", "password": "AnyPassword"},
        )
        assert resp.status_code == 401
        # Must NOT reveal which field was wrong
        assert "email" not in resp.text.lower() or "password" not in resp.text.lower()

    @pytest.mark.asyncio
    async def test_inactive_user_returns_401(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        from uuid import uuid4

        inactive = User(
            id=uuid4(),
            email="inactive@test.com",
            hashed_password=hash_password("Secure1234!"),
            full_name="Inactive User",
            role=UserRole.EXAMINER.value,
            is_active=False,
        )
        test_db_session.add(inactive)
        await test_db_session.commit()

        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@test.com", "password": "Secure1234!"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: Successful login and /me
# ---------------------------------------------------------------------------


class TestSuccessfulLogin:
    @pytest.mark.asyncio
    async def test_valid_login_returns_token(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        await _create_user(test_db_session, email="bob@test.com")
        await test_db_session.commit()

        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "bob@test.com", "password": "Secure1234!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "bob@test.com"

    @pytest.mark.asyncio
    async def test_me_returns_user_profile(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        await _create_user(test_db_session, email="carol@test.com")
        await test_db_session.commit()

        token = await _login(async_client, "carol@test.com")
        resp = await async_client.get("/api/v1/auth/me", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == "carol@test.com"


# ---------------------------------------------------------------------------
# Test: Case CRUD
# ---------------------------------------------------------------------------


class TestCaseCRUD:
    @pytest.mark.asyncio
    async def test_create_case_as_examiner(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        await _create_user(test_db_session, email="examiner@test.com")
        await test_db_session.commit()

        token = await _login(async_client, "examiner@test.com")
        resp = await async_client.post(
            "/api/v1/cases",
            json={"case_number": "CAS-2026-0001", "title": "My First Case"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["case_number"] == "CAS-2026-0001"
        assert body["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_create_case_with_duplicate_number_returns_409(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        user = await _create_user(test_db_session, email="dup@test.com")
        await _create_case(test_db_session, case_number="CAS-2026-DUPE", lead_id=user.id)
        await test_db_session.commit()

        token = await _login(async_client, "dup@test.com")
        resp = await async_client.post(
            "/api/v1/cases",
            json={"case_number": "CAS-2026-DUPE", "title": "Duplicate"},
            headers=_auth(token),
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        await _create_user(test_db_session, email="viewer@test.com", role=UserRole.VIEWER)
        await test_db_session.commit()

        token = await _login(async_client, "viewer@test.com")
        resp = await async_client.post(
            "/api/v1/cases",
            json={"case_number": "CAS-VIEWER", "title": "Viewer Attempt"},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_cases_pagination(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        user = await _create_user(test_db_session, email="paginate@test.com")
        for i in range(5):
            await _create_case(
                test_db_session, case_number=f"CAS-PAGE-{i:03}", lead_id=user.id
            )
        await test_db_session.commit()

        token = await _login(async_client, "paginate@test.com")
        resp = await async_client.get(
            "/api/v1/cases?page=1&page_size=3",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 3
        assert len(body["items"]) == 3
        assert body["total"] >= 5


# ---------------------------------------------------------------------------
# Test: Case-level authorization
# ---------------------------------------------------------------------------


class TestCaseAuthorization:
    @pytest.mark.asyncio
    async def test_examiner_can_access_own_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        user = await _create_user(test_db_session, email="own@test.com")
        case = await _create_case(test_db_session, case_number="CAS-OWN-001", lead_id=user.id)
        await test_db_session.commit()

        token = await _login(async_client, "own@test.com")
        resp = await async_client.get(f"/api/v1/cases/{case.id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == str(case.id)

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_another_users_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        """Core security test: another examiner's case must return 403."""
        owner = await _create_user(test_db_session, email="owner@test.com")
        attacker = await _create_user(test_db_session, email="attacker@test.com")
        case = await _create_case(
            test_db_session, case_number="CAS-SECRET-001", lead_id=owner.id
        )
        await test_db_session.commit()

        # Attacker tries to read owner's case
        token = await _login(async_client, "attacker@test.com")
        resp = await async_client.get(f"/api/v1/cases/{case.id}", headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "CASE_ACCESS_DENIED"

    @pytest.mark.asyncio
    async def test_admin_can_access_any_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(test_db_session, email="case_owner@test.com")
        admin = await _create_user(
            test_db_session, email="admin@test.com", role=UserRole.ADMIN
        )
        case = await _create_case(
            test_db_session, case_number="CAS-ADMIN-ACCESS", lead_id=owner.id
        )
        await test_db_session.commit()

        token = await _login(async_client, "admin@test.com")
        resp = await async_client.get(f"/api/v1/cases/{case.id}", headers=_auth(token))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_examiner_cannot_update_another_users_case(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(test_db_session, email="update_owner@test.com")
        attacker = await _create_user(test_db_session, email="update_attacker@test.com")
        case = await _create_case(
            test_db_session, case_number="CAS-UPDATE-DENY", lead_id=owner.id
        )
        await test_db_session.commit()

        token = await _login(async_client, "update_attacker@test.com")
        resp = await async_client.patch(
            f"/api/v1/cases/{case.id}",
            json={"title": "Stolen Update"},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_examiner_list_only_sees_own_cases(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        user_a = await _create_user(test_db_session, email="list_a@test.com")
        user_b = await _create_user(test_db_session, email="list_b@test.com")
        await _create_case(test_db_session, case_number="CAS-A-001", lead_id=user_a.id)
        await _create_case(test_db_session, case_number="CAS-B-001", lead_id=user_b.id)
        await test_db_session.commit()

        token = await _login(async_client, "list_a@test.com")
        resp = await async_client.get("/api/v1/cases", headers=_auth(token))
        assert resp.status_code == 200
        case_numbers = [c["case_number"] for c in resp.json()["items"]]
        assert "CAS-A-001" in case_numbers
        assert "CAS-B-001" not in case_numbers
