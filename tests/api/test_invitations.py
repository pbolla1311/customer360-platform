"""Invitation lifecycle tests: invite -> accept/revoke/expiry, plus the
Admin-only enforcement on inviting/revoking.
"""

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("API_KEY", "test-api-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from customer360.api.main import app  # noqa: E402
from customer360.api.pipeline_simulation_engine import ENGINE  # noqa: E402
from customer360.api.rate_limit import limiter  # noqa: E402
from customer360.infrastructure.session import Base, get_db_session  # noqa: E402
from customer360.tenancy.repository import (  # noqa: E402
    InvitationRepository,
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)


def _fresh_db():
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


def _admin_client():
    override, factory = _fresh_db()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)

    seed_session = factory()
    org = OrganizationRepository(seed_session).create("Acme Corporation")
    admin = UserRepository(seed_session).create("Sarah Johnson", "sarah@acme.test")
    MembershipRepository(seed_session).create(admin.id, org.id, "admin")
    seed_session.close()

    login = client.post("/demo/api/auth/login", json={"user_id": admin.id})
    assert login.status_code == 200

    return client, factory, org, admin


def _teardown():
    app.dependency_overrides.pop(get_db_session, None)
    ENGINE.reset()
    limiter.reset()


def test_admin_can_invite_a_user():
    client, _factory, org, _admin = _admin_client()
    try:
        response = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "jordan@acme.test"
        assert body["role"] == "viewer"
        assert body["status"] == "pending"
        assert body["invited_by"] == "Sarah Johnson"
    finally:
        _teardown()


def test_non_admin_cannot_invite_a_user():
    client, factory, org, _admin = _admin_client()
    try:
        seed_session = factory()
        viewer = UserRepository(seed_session).create("Jordan Lee", "jordan@acme.test")
        MembershipRepository(seed_session).create(viewer.id, org.id, "viewer")
        seed_session.close()

        client.post("/demo/api/auth/login", json={"user_id": viewer.id})
        response = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "new@acme.test", "role": "viewer"},
        )
        assert response.status_code == 403
    finally:
        _teardown()


def test_accepting_an_invitation_creates_user_and_membership():
    client, factory, org, _admin = _admin_client()
    try:
        invite = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        ).json()

        response = client.post(f"/demo/api/invitations/{invite['id']}/accept")
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

        seed_session = factory()
        new_user = UserRepository(seed_session).get_by_email("jordan@acme.test")
        assert new_user is not None
        membership = MembershipRepository(seed_session).get(new_user.id, org.id)
        assert membership is not None
        assert membership.role == "viewer"
        seed_session.close()
    finally:
        _teardown()


def test_accepting_an_invitation_lets_the_new_user_log_in():
    client, _factory, org, _admin = _admin_client()
    try:
        invite = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        ).json()
        client.post(f"/demo/api/invitations/{invite['id']}/accept")

        users = client.get("/demo/api/auth/users").json()
        jordan = next(u for u in users if u["email"] == "jordan@acme.test")

        new_client = TestClient(app)
        login = new_client.post("/demo/api/auth/login", json={"user_id": jordan["id"]})
        assert login.status_code == 200
        assert login.json()["role"] == "viewer"
        assert login.json()["organization"]["id"] == org.id
    finally:
        _teardown()


def test_accepting_an_already_accepted_invitation_returns_409():
    client, _factory, org, _admin = _admin_client()
    try:
        invite = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        ).json()
        client.post(f"/demo/api/invitations/{invite['id']}/accept")

        second_attempt = client.post(f"/demo/api/invitations/{invite['id']}/accept")
        assert second_attempt.status_code == 409
    finally:
        _teardown()


def test_accepting_an_unknown_invitation_returns_404():
    client, _factory, _org, _admin = _admin_client()
    try:
        response = client.post("/demo/api/invitations/999999/accept")
        assert response.status_code == 404
    finally:
        _teardown()


def test_admin_can_revoke_a_pending_invitation():
    client, _factory, org, _admin = _admin_client()
    try:
        invite = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        ).json()

        response = client.post(f"/demo/api/invitations/{invite['id']}/revoke")
        assert response.status_code == 200
        assert response.json()["status"] == "revoked"

        # A revoked invitation can no longer be accepted.
        accept_attempt = client.post(f"/demo/api/invitations/{invite['id']}/accept")
        assert accept_attempt.status_code == 409
    finally:
        _teardown()


def test_non_admin_cannot_revoke_an_invitation():
    client, factory, org, _admin = _admin_client()
    try:
        invite = client.post(
            f"/demo/api/organizations/{org.id}/invitations",
            json={"email": "jordan@acme.test", "role": "viewer"},
        ).json()

        seed_session = factory()
        viewer = UserRepository(seed_session).create("Viewer User", "viewer@acme.test")
        MembershipRepository(seed_session).create(viewer.id, org.id, "viewer")
        seed_session.close()

        viewer_client = TestClient(app)
        viewer_client.post("/demo/api/auth/login", json={"user_id": viewer.id})
        response = viewer_client.post(f"/demo/api/invitations/{invite['id']}/revoke")
        assert response.status_code == 403
    finally:
        _teardown()


def test_expired_pending_invitation_shows_as_expired_in_listing():
    client, factory, org, _admin = _admin_client()
    try:
        seed_session = factory()
        invitation_repo = InvitationRepository(seed_session)
        invitation_repo.create(
            organization_id=org.id,
            email="stale@acme.test",
            role="viewer",
            invited_by_user_id=None,
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        seed_session.close()

        invitations = client.get(f"/demo/api/organizations/{org.id}/invitations").json()
        assert invitations[0]["status"] == "expired"
    finally:
        _teardown()


def test_list_invitations_for_a_different_organization_returns_403():
    client, factory, org, _admin = _admin_client()
    try:
        seed_session = factory()
        other_org = OrganizationRepository(seed_session).create("Globex")
        seed_session.close()

        response = client.get(f"/demo/api/organizations/{other_org.id}/invitations")
        assert response.status_code == 403
    finally:
        _teardown()
