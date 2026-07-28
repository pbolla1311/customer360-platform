"""RBAC tests: the pure NAV_PERMISSIONS/CAN_* matrix in
customer360/tenancy/permissions.py, plus endpoint-level 403 enforcement
for privileged actions (customer edits, pipeline operations, organization
management) across all 5 roles.
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
from customer360.tenancy.permissions import Role, can_view, has_permission  # noqa: E402
from customer360.tenancy.repository import (  # noqa: E402
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)

# ---------------------------------------------------------------------
# Pure permission matrix
# ---------------------------------------------------------------------


def test_admin_can_perform_every_privileged_action():
    for action in ("customers.edit", "pipeline.operate", "organization.manage"):
        assert has_permission(Role.ADMIN, action) is True


def test_operations_can_only_operate_pipeline():
    assert has_permission(Role.OPERATIONS, "pipeline.operate") is True
    assert has_permission(Role.OPERATIONS, "customers.edit") is False
    assert has_permission(Role.OPERATIONS, "organization.manage") is False


def test_customer_success_can_only_edit_customers():
    assert has_permission(Role.CUSTOMER_SUCCESS, "customers.edit") is True
    assert has_permission(Role.CUSTOMER_SUCCESS, "pipeline.operate") is False
    assert has_permission(Role.CUSTOMER_SUCCESS, "organization.manage") is False


def test_executive_and_viewer_cannot_perform_any_privileged_action():
    for role in (Role.EXECUTIVE, Role.VIEWER):
        for action in ("customers.edit", "pipeline.operate", "organization.manage"):
            assert has_permission(role, action) is False


def test_has_permission_fails_closed_for_unknown_role_or_action():
    assert has_permission("not-a-real-role", "customers.edit") is False
    assert has_permission(None, "customers.edit") is False
    assert has_permission(Role.ADMIN, "not-a-real-action") is False


def test_can_view_matches_nav_permissions_matrix():
    assert can_view(Role.VIEWER, "customers") is True
    assert can_view(Role.OPERATIONS, "customers") is False
    assert can_view(Role.EXECUTIVE, "analytics") is True
    assert can_view(Role.OPERATIONS, "analytics") is False
    assert can_view(Role.ADMIN, "settings") is True
    assert can_view(Role.VIEWER, "settings") is False


def test_can_view_fails_closed_for_unknown_role_or_view():
    assert can_view("not-a-real-role", "overview") is False
    assert can_view(Role.ADMIN, "not-a-real-view") is False


# ---------------------------------------------------------------------
# Endpoint-level enforcement across all 5 roles
# ---------------------------------------------------------------------


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


def _client_signed_in_as(role: str):
    """A fresh client + DB, signed in as a fresh user with the given role
    in a fresh organization that owns one customer."""

    override, factory = _fresh_db()
    app.dependency_overrides[get_db_session] = override
    client = TestClient(app)

    seed_session = factory()
    org = OrganizationRepository(seed_session).create("Acme Corporation")
    user = UserRepository(seed_session).create(f"{role.title()} User", f"{role}@acme.test")
    MembershipRepository(seed_session).create(user.id, org.id, role)
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

    login = client.post("/demo/api/auth/login", json={"user_id": user.id})
    assert login.status_code == 200

    return client, org


def _teardown():
    app.dependency_overrides.pop(get_db_session, None)
    ENGINE.reset()
    # This file logs in ~25 times across its tests, all from the same
    # TestClient "IP" -- without resetting, slowapi's shared in-memory
    # rate-limit storage (keyed process-wide, not per-TestClient-instance)
    # eventually 429s the /demo/api/auth/login calls in later tests.
    limiter.reset()


ALL_ROLES = ["admin", "operations", "customer_success", "executive", "viewer"]


def test_patch_customer_allowed_only_for_admin_and_customer_success():
    for role in ALL_ROLES:
        client, _org = _client_signed_in_as(role)
        try:
            response = client.patch(
                "/demo/api/customers/ACME-0001", json={"city": "Manchester"}
            )
            if role in ("admin", "customer_success"):
                assert response.status_code == 200, role
            else:
                assert response.status_code == 403, role
        finally:
            _teardown()


def test_pipeline_operate_actions_allowed_only_for_admin_and_operations():
    for role in ALL_ROLES:
        client, _org = _client_signed_in_as(role)
        try:
            response = client.post(
                "/demo/api/pipeline/failure", json={"failure_type": "consumer_failure"}
            )
            if role in ("admin", "operations"):
                assert response.status_code == 200, role
            else:
                assert response.status_code == 403, role
        finally:
            _teardown()


def test_pipeline_recover_and_reset_allowed_only_for_admin_and_operations():
    for role in ALL_ROLES:
        client, _org = _client_signed_in_as(role)
        try:
            recover = client.post("/demo/api/pipeline/recover")
            reset = client.post("/demo/api/pipeline/reset")
            if role in ("admin", "operations"):
                assert recover.status_code == 200, role
                assert reset.status_code == 200, role
            else:
                assert recover.status_code == 403, role
                assert reset.status_code == 403, role
        finally:
            _teardown()


def test_organization_management_allowed_only_for_admin():
    for role in ALL_ROLES:
        client, org = _client_signed_in_as(role)
        try:
            response = client.post(
                f"/demo/api/organizations/{org.id}/invitations",
                json={"email": "new@acme.test", "role": "viewer"},
            )
            if role == "admin":
                assert response.status_code == 200, role
            else:
                assert response.status_code == 403, role
        finally:
            _teardown()


def test_pipeline_generate_and_replay_remain_ungated_for_every_role():
    """Deliberately NOT in CAN_OPERATE_PIPELINE's scope (see main.py's
    _require_pipeline_permission docstring) -- every role can still use
    them, matching the approved v3.5 scope."""

    for role in ALL_ROLES:
        client, _org = _client_signed_in_as(role)
        try:
            assert client.post("/demo/api/pipeline/generate").status_code == 200, role
            assert client.post("/demo/api/pipeline/replay").status_code == 200, role
        finally:
            _teardown()
