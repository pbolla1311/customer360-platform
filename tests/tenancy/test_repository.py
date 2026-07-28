"""CRUD tests for the v3.5 multi-tenancy repositories. Uses the same
function-scoped in-memory-SQLite `session` fixture as
tests/infrastructure/test_repository.py (defined once in tests/conftest.py).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from customer360.tenancy.repository import (
    ApiKeyRepository,
    InvitationRepository,
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)

# ---------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------


def test_organization_create_generates_slug(session: Session):
    org = OrganizationRepository(session).create("Acme Corporation")

    assert org.id is not None
    assert org.slug == "acme-corporation"
    assert org.theme == "dark"


def test_organization_create_dedupes_slug_collisions(session: Session):
    repo = OrganizationRepository(session)
    first = repo.create("Acme Corporation")
    second = repo.create("Acme Corporation")

    assert first.slug == "acme-corporation"
    assert second.slug == "acme-corporation-2"


def test_organization_get_by_id_and_slug(session: Session):
    repo = OrganizationRepository(session)
    org = repo.create("Globex")

    assert repo.get_by_id(org.id) is org
    assert repo.get_by_slug("globex").id == org.id
    assert repo.get_by_id(999999) is None
    assert repo.get_by_slug("nonexistent") is None


def test_organization_list_for_user_only_returns_memberships(session: Session):
    org_repo = OrganizationRepository(session)
    user_repo = UserRepository(session)
    membership_repo = MembershipRepository(session)

    acme = org_repo.create("Acme")
    globex = org_repo.create("Globex")
    user = user_repo.create("Sarah Johnson", "sarah@acme.test")

    membership_repo.create(user.id, acme.id, "admin")

    orgs = org_repo.list_for_user(user.id)
    assert [o.id for o in orgs] == [acme.id]
    assert globex.id not in [o.id for o in orgs]


def test_organization_update_branding(session: Session):
    repo = OrganizationRepository(session)
    org = repo.create("Acme")

    updated = repo.update_branding(org, name="Acme Inc", logo_url="https://x/logo.png", theme="light")

    assert updated.name == "Acme Inc"
    assert updated.logo_url == "https://x/logo.png"
    assert updated.theme == "light"


# ---------------------------------------------------------------------
# User
# ---------------------------------------------------------------------


def test_user_create_and_lookup(session: Session):
    repo = UserRepository(session)
    user = repo.create("Sarah Johnson", "sarah@acme.test")

    assert repo.get_by_id(user.id).email == "sarah@acme.test"
    assert repo.get_by_email("sarah@acme.test").id == user.id
    assert repo.get_by_email("missing@acme.test") is None


def test_user_list_all_orders_by_name(session: Session):
    repo = UserRepository(session)
    repo.create("Zed", "zed@acme.test")
    repo.create("Ann", "ann@acme.test")

    names = [u.name for u in repo.list_all()]
    assert names == ["Ann", "Zed"]


def test_user_touch_last_login_sets_timestamp(session: Session):
    repo = UserRepository(session)
    user = repo.create("Sarah Johnson", "sarah@acme.test")
    assert user.last_login_at is None

    updated = repo.touch_last_login(user)
    assert updated.last_login_at is not None


# ---------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------


def test_membership_create_and_get(session: Session):
    org = OrganizationRepository(session).create("Acme")
    user = UserRepository(session).create("Sarah Johnson", "sarah@acme.test")
    membership_repo = MembershipRepository(session)

    created = membership_repo.create(user.id, org.id, "admin")

    assert membership_repo.get_by_id(created.id).role == "admin"
    assert membership_repo.get(user.id, org.id).id == created.id
    assert membership_repo.get(user.id, 999999) is None


def test_membership_list_for_user(session: Session):
    org_repo = OrganizationRepository(session)
    user = UserRepository(session).create("Sarah Johnson", "sarah@acme.test")
    membership_repo = MembershipRepository(session)

    acme = org_repo.create("Acme")
    globex = org_repo.create("Globex")
    membership_repo.create(user.id, acme.id, "admin")
    membership_repo.create(user.id, globex.id, "viewer")

    memberships = membership_repo.list_for_user(user.id)
    assert {m.organization_id for m in memberships} == {acme.id, globex.id}


def test_membership_list_members_joins_user_data(session: Session):
    org = OrganizationRepository(session).create("Acme")
    user_repo = UserRepository(session)
    membership_repo = MembershipRepository(session)

    sarah = user_repo.create("Sarah Johnson", "sarah@acme.test")
    mike = user_repo.create("Mike Torres", "mike@acme.test")
    membership_repo.create(sarah.id, org.id, "admin")
    membership_repo.create(mike.id, org.id, "operations")

    rows = membership_repo.list_members(org.id)
    names = sorted(user.name for _membership, user in rows)
    assert names == ["Mike Torres", "Sarah Johnson"]


def test_membership_update_role(session: Session):
    org = OrganizationRepository(session).create("Acme")
    user = UserRepository(session).create("Sarah Johnson", "sarah@acme.test")
    membership_repo = MembershipRepository(session)
    membership = membership_repo.create(user.id, org.id, "viewer")

    updated = membership_repo.update_role(membership, "admin")
    assert updated.role == "admin"


def test_membership_delete_removes_row(session: Session):
    org = OrganizationRepository(session).create("Acme")
    user = UserRepository(session).create("Sarah Johnson", "sarah@acme.test")
    membership_repo = MembershipRepository(session)
    membership = membership_repo.create(user.id, org.id, "viewer")

    membership_repo.delete(membership)

    assert membership_repo.get_by_id(membership.id) is None


# ---------------------------------------------------------------------
# Invitation
# ---------------------------------------------------------------------


def test_invitation_create_defaults_to_pending(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = InvitationRepository(session)

    invitation = repo.create(
        organization_id=org.id,
        email="jordan@acme.test",
        role="viewer",
        invited_by_user_id=None,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )

    assert invitation.status == "pending"
    assert invitation.accepted_at is None


def test_invitation_list_for_organization_most_recent_first(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = InvitationRepository(session)
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)

    first = repo.create(
        organization_id=org.id, email="a@acme.test", role="viewer",
        invited_by_user_id=None, expires_at=expires,
    )
    second = repo.create(
        organization_id=org.id, email="b@acme.test", role="viewer",
        invited_by_user_id=None, expires_at=expires,
    )

    invitations = repo.list_for_organization(org.id)
    assert invitations[0].id == second.id
    assert invitations[1].id == first.id


def test_invitation_mark_accepted_and_revoked(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = InvitationRepository(session)
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)

    accepted = repo.create(
        organization_id=org.id, email="a@acme.test", role="viewer",
        invited_by_user_id=None, expires_at=expires,
    )
    revoked = repo.create(
        organization_id=org.id, email="b@acme.test", role="viewer",
        invited_by_user_id=None, expires_at=expires,
    )

    updated_accepted = repo.mark_accepted(accepted)
    updated_revoked = repo.mark_revoked(revoked)

    assert updated_accepted.status == "accepted"
    assert updated_accepted.accepted_at is not None
    assert updated_revoked.status == "revoked"


# ---------------------------------------------------------------------
# ApiKey
# ---------------------------------------------------------------------


def test_api_key_create_and_lookup(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = ApiKeyRepository(session)

    created = repo.create(
        organization_id=org.id, name="Production", key_prefix="sk_live_ab…", hashed_key="hash1"
    )

    assert repo.get_by_id(created.id).name == "Production"
    assert repo.get_by_hash("hash1").id == created.id
    assert repo.get_by_hash("missing") is None


def test_api_key_mark_used_sets_timestamp(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = ApiKeyRepository(session)
    key = repo.create(organization_id=org.id, name="Prod", key_prefix="p", hashed_key="h")
    assert key.last_used_at is None

    updated = repo.mark_used(key)
    assert updated.last_used_at is not None


def test_api_key_rotate_replaces_material_and_clears_last_used(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = ApiKeyRepository(session)
    key = repo.create(organization_id=org.id, name="Prod", key_prefix="old", hashed_key="oldhash")
    repo.mark_used(key)

    rotated = repo.rotate(key, key_prefix="new", hashed_key="newhash")

    assert rotated.key_prefix == "new"
    assert rotated.hashed_key == "newhash"
    assert rotated.last_used_at is None
    assert repo.get_by_hash("oldhash") is None


def test_api_key_revoke_sets_status(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = ApiKeyRepository(session)
    key = repo.create(organization_id=org.id, name="Prod", key_prefix="p", hashed_key="h")

    revoked = repo.revoke(key)
    assert revoked.status == "revoked"


def test_api_key_list_for_organization_most_recent_first(session: Session):
    org = OrganizationRepository(session).create("Acme")
    repo = ApiKeyRepository(session)
    first = repo.create(organization_id=org.id, name="First", key_prefix="a", hashed_key="ha")
    second = repo.create(organization_id=org.id, name="Second", key_prefix="b", hashed_key="hb")

    keys = repo.list_for_organization(org.id)
    assert keys[0].id == second.id
    assert keys[1].id == first.id
