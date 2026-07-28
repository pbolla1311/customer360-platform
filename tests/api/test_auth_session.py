"""Demo-tier session/auth tests: login/logout/session/switch-workspace/
org-signup, plus the "no session -> byte-identical to before v3.5"
regression cases for /demo/api/customers and /demo/api/pipeline/history.

Each test gets its own TestClient (module-level `client` instances in
other test files persist cookies across tests, which would leak session
state between tests here) and its own shared in-memory SQLite DB (same
pattern as test_main.py's `_shared_sqlite_session_override`).
"""

import os

os.environ.setdefault("API_KEY", "test-api-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from customer360.api.main import app  # noqa: E402
from customer360.api.pipeline_simulation_engine import ENGINE  # noqa: E402
from customer360.api.rate_limit import limiter  # noqa: E402
from customer360.infrastructure.models import Customer360Profile  # noqa: E402
from customer360.infrastructure.repository import Customer360Repository  # noqa: E402
from customer360.infrastructure.session import Base, get_db_session  # noqa: E402
from customer360.tenancy.repository import (  # noqa: E402
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)


def _fresh_db():
    """One shared in-memory DB per test, kept alive across requests within
    that test (a real per-process app has exactly this: one long-lived DB
    across many short-lived per-request sessions)."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    return _override, factory


def _seeded_client():
    """A fresh TestClient + DB with one organization/user/membership
    already in place (Acme / Sarah Johnson / admin), plus one seeded
    customer belonging to that org -- the common starting point most
    tests below build on."""

    override, factory = _fresh_db()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)

    seed_session = factory()
    org = OrganizationRepository(seed_session).create("Acme Corporation")
    user = UserRepository(seed_session).create("Sarah Johnson", "sarah@acme.test")
    MembershipRepository(seed_session).create(user.id, org.id, "admin")
    Customer360Repository(seed_session).create(
        Customer360Profile(
            customer_id="ACME-0001",
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            city="London",
            state="LDN",
            transaction_count=2,
            total_spend=42.0,
            average_transaction_value=21.0,
            organization_id=org.id,
        )
    )
    seed_session.close()

    return client, factory, org, user


def _teardown():
    app.dependency_overrides.pop(get_db_session, None)
    ENGINE.reset()
    # slowapi's rate-limit storage is shared process-wide (keyed by
    # TestClient's fixed "testclient" address), not per-TestClient-instance
    # -- reset it so this file's many /demo/api/auth/login calls never
    # spuriously 429, regardless of what other test files ran before it.
    limiter.reset()


# ---------------------------------------------------------------------
# Login / session / logout
# ---------------------------------------------------------------------


def test_login_unknown_user_returns_404():
    client, _factory, _org, _user = _seeded_client()
    try:
        response = client.post("/demo/api/auth/login", json={"user_id": 999999})
        assert response.status_code == 404
    finally:
        _teardown()


def test_login_user_with_no_memberships_returns_400():
    override, factory = _fresh_db()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)
    try:
        seed_session = factory()
        lonely_user = UserRepository(seed_session).create("Nobody", "nobody@nowhere.test")
        seed_session.close()

        response = client.post("/demo/api/auth/login", json={"user_id": lonely_user.id})
        assert response.status_code == 400
    finally:
        _teardown()


def test_login_with_single_membership_auto_selects_organization():
    client, _factory, org, user = _seeded_client()
    try:
        response = client.post("/demo/api/auth/login", json={"user_id": user.id})
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["name"] == "Sarah Johnson"
        assert body["organization"]["id"] == org.id
        assert body["role"] == "admin"
    finally:
        _teardown()


def test_login_with_multiple_memberships_requires_workspace_selection():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        globex = OrganizationRepository(seed_session).create("Globex")
        MembershipRepository(seed_session).create(user.id, globex.id, "viewer")
        seed_session.close()

        response = client.post("/demo/api/auth/login", json={"user_id": user.id})
        assert response.status_code == 200
        body = response.json()
        assert body["organization"] is None
        assert body["role"] is None
        org_ids = {o["id"] for o in body["available_organizations"]}
        assert org_ids == {org.id, globex.id}
    finally:
        _teardown()


def test_login_with_explicit_organization_id_selects_it():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        globex = OrganizationRepository(seed_session).create("Globex")
        MembershipRepository(seed_session).create(user.id, globex.id, "viewer")
        seed_session.close()

        response = client.post(
            "/demo/api/auth/login", json={"user_id": user.id, "organization_id": globex.id}
        )
        assert response.status_code == 200
        assert response.json()["organization"]["id"] == globex.id
        assert response.json()["role"] == "viewer"
    finally:
        _teardown()


def test_switch_workspace_updates_session():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        globex = OrganizationRepository(seed_session).create("Globex")
        MembershipRepository(seed_session).create(user.id, globex.id, "operations")
        seed_session.close()

        client.post("/demo/api/auth/login", json={"user_id": user.id, "organization_id": org.id})
        response = client.post(
            "/demo/api/auth/switch-workspace", json={"organization_id": globex.id}
        )
        assert response.status_code == 200
        assert response.json()["organization"]["id"] == globex.id
        assert response.json()["role"] == "operations"
    finally:
        _teardown()


def test_switch_workspace_rejects_non_member_organization():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        other_org = OrganizationRepository(seed_session).create("Not Mine")
        seed_session.close()

        client.post("/demo/api/auth/login", json={"user_id": user.id, "organization_id": org.id})
        response = client.post(
            "/demo/api/auth/switch-workspace", json={"organization_id": other_org.id}
        )
        assert response.status_code == 403
    finally:
        _teardown()


def test_switch_workspace_without_login_returns_401():
    client, _factory, _org, _user = _seeded_client()
    try:
        response = client.post("/demo/api/auth/switch-workspace", json={"organization_id": 1})
        assert response.status_code == 401
    finally:
        _teardown()


def test_session_endpoint_reflects_signed_in_state():
    client, _factory, org, user = _seeded_client()
    try:
        assert client.get("/demo/api/auth/session").json()["user"] is None

        client.post("/demo/api/auth/login", json={"user_id": user.id})
        body = client.get("/demo/api/auth/session").json()
        assert body["user"]["id"] == user.id
        assert body["organization"]["id"] == org.id
    finally:
        _teardown()


def test_logout_clears_session():
    client, _factory, _org, user = _seeded_client()
    try:
        client.post("/demo/api/auth/login", json={"user_id": user.id})
        client.post("/demo/api/auth/logout")
        assert client.get("/demo/api/auth/session").json()["user"] is None
    finally:
        _teardown()


# ---------------------------------------------------------------------
# Organization signup ("a company signs up")
# ---------------------------------------------------------------------


def test_create_organization_signs_up_admin_and_sets_session():
    override, _factory = _fresh_db()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)
    try:
        response = client.post(
            "/demo/api/organizations",
            json={
                "name": "Brand New Co",
                "admin_name": "Taylor Admin",
                "admin_email": "taylor@brandnew.test",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["organization"]["name"] == "Brand New Co"
        assert body["role"] == "admin"

        session_body = client.get("/demo/api/auth/session").json()
        assert session_body["user"]["name"] == "Taylor Admin"
    finally:
        _teardown()


def test_create_organization_rejects_duplicate_admin_email():
    client, _factory, _org, user = _seeded_client()
    try:
        response = client.post(
            "/demo/api/organizations",
            json={"name": "Another Co", "admin_name": "Someone", "admin_email": user.email},
        )
        assert response.status_code == 409
    finally:
        _teardown()


# ---------------------------------------------------------------------
# Regression: no session -> byte-identical to pre-v3.5 behavior
# ---------------------------------------------------------------------


def test_demo_customers_unscoped_without_session_matches_pre_v35_behavior():
    client, _factory, _org, _user = _seeded_client()
    try:
        response = client.get("/demo/api/customers")
        assert response.status_code == 200
        assert len(response.json()) == 1
    finally:
        _teardown()


def test_demo_customers_scoped_with_session_shows_only_own_organization():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        other_org = OrganizationRepository(seed_session).create("Globex")
        Customer360Repository(seed_session).create(
            Customer360Profile(
                customer_id="GLOBEX-0001",
                first_name="Hank",
                last_name="Scorpio",
                email="hank@example.com",
                city="Cypress Creek",
                state="TX",
                transaction_count=1,
                total_spend=1.0,
                average_transaction_value=1.0,
                organization_id=other_org.id,
            )
        )
        seed_session.close()

        # No session: sees both organizations' customers, unchanged.
        assert len(client.get("/demo/api/customers").json()) == 2

        client.post("/demo/api/auth/login", json={"user_id": user.id, "organization_id": org.id})
        scoped = client.get("/demo/api/customers").json()
        assert len(scoped) == 1
        assert scoped[0]["customer_id"] == "ACME-0001"
    finally:
        _teardown()


def test_demo_customer_detail_404s_for_a_different_organizations_customer():
    client, factory, org, user = _seeded_client()
    try:
        seed_session = factory()
        other_org = OrganizationRepository(seed_session).create("Globex")
        Customer360Repository(seed_session).create(
            Customer360Profile(
                customer_id="GLOBEX-0001",
                first_name="Hank",
                last_name="Scorpio",
                email="hank@example.com",
                city="Cypress Creek",
                state="TX",
                transaction_count=1,
                total_spend=1.0,
                average_transaction_value=1.0,
                organization_id=other_org.id,
            )
        )
        seed_session.close()

        client.post("/demo/api/auth/login", json={"user_id": user.id, "organization_id": org.id})

        assert client.get("/demo/api/customers/ACME-0001").status_code == 200
        assert client.get("/demo/api/customers/GLOBEX-0001").status_code == 404
    finally:
        _teardown()


def test_pipeline_history_unscoped_without_session_matches_pre_v35_behavior():
    client, _factory, _org, _user = _seeded_client()
    try:
        client.post("/demo/api/pipeline/generate")
        response = client.get("/demo/api/pipeline/history")
        assert response.status_code == 200
        assert len(response.json()) == 1
    finally:
        _teardown()


def test_pipeline_history_scoped_shows_own_org_events_plus_shared_demo_events():
    client, factory, org, user = _seeded_client()
    try:
        # A Control Center demo event -- organization_id stays None (shared).
        client.post("/demo/api/pipeline/generate")

        client.post("/demo/api/auth/login", json={"user_id": user.id, "organization_id": org.id})
        client.patch("/demo/api/customers/ACME-0001", json={"city": "Manchester"})

        history = client.get("/demo/api/pipeline/history").json()
        assert len(history) == 2
        assert {entry["event"]["organization_id"] for entry in history} == {None, org.id}
    finally:
        _teardown()
