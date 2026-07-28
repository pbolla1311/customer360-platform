"""Seed fictional multi-tenancy demo data for Customer360 Cloud (v3.5):
a few organizations, users, memberships, and invitations, so the
Workspace's login screen, workspace switcher, and Settings > Users/
Invitations tabs have real data on first load.

Idempotent: running this repeatedly looks up existing rows by their
natural key (organization slug, user email) and skips creating
duplicates. Disabled by default -- same opt-in convention as
seed_demo_customers.py:

    ENABLE_DEMO_SEED=true python scripts/seed_demo_tenancy.py

or:

    python scripts/seed_demo_tenancy.py --force

All records use reserved example domains and fictional names -- no real
personal information. Intended to run after seed_demo_customers.py (which
seeds the DEMO-0001..0010 rows that the migration backfilled into the
"Demo Workspace" organization) -- this script leaves that organization
and its customers untouched, and adds two more organizations (Acme
Corporation, Globex Corporation) with a couple of their own customers, so
switching workspaces visibly changes the Customers list.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import SessionLocal
from customer360.tenancy.models import Organization, User
from customer360.tenancy.repository import (
    InvitationRepository,
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)

ORGANIZATIONS: list[dict[str, str]] = [
    {"name": "Acme Corporation", "slug": "acme-corporation"},
    {"name": "Globex Corporation", "slug": "globex-corporation"},
]

USERS: list[dict[str, str]] = [
    {"name": "Sarah Johnson", "email": "sarah.johnson@example.com", "avatar_color": "#3b82f6"},
    {"name": "Mike Torres", "email": "mike.torres@example.com", "avatar_color": "#22d3ee"},
    {"name": "Priya Patel", "email": "priya.patel@example.com", "avatar_color": "#a78bfa"},
    {"name": "Alex Kim", "email": "alex.kim@example.com", "avatar_color": "#34d399"},
    {"name": "Jordan Lee", "email": "jordan.lee@example.com", "avatar_color": "#fbbf24"},
]

# (user email, organization slug, role). Sarah Johnson is Admin across all
# three organizations (including the pre-existing "Demo Workspace"),
# demonstrating the workspace switcher; everyone else belongs to Acme only.
MEMBERSHIPS: list[tuple[str, str, str]] = [
    ("sarah.johnson@example.com", "acme-corporation", "admin"),
    ("sarah.johnson@example.com", "globex-corporation", "admin"),
    ("sarah.johnson@example.com", "demo-workspace", "admin"),
    ("mike.torres@example.com", "acme-corporation", "operations"),
    ("priya.patel@example.com", "acme-corporation", "customer_success"),
    ("alex.kim@example.com", "acme-corporation", "executive"),
    ("jordan.lee@example.com", "acme-corporation", "viewer"),
]

ACME_CUSTOMERS: list[dict[str, object]] = [
    {
        "customer_id": "ACME-0001",
        "first_name": "Dana",
        "last_name": "Whitfield",
        "email": "dana.whitfield@example.com",
        "city": "New York",
        "state": "NY",
        "transaction_count": 12,
        "total_spend": 2140.50,
        "average_transaction_value": 178.38,
    },
    {
        "customer_id": "ACME-0002",
        "first_name": "Owen",
        "last_name": "Bianchi",
        "email": "owen.bianchi@example.com",
        "city": "Miami",
        "state": "FL",
        "transaction_count": 4,
        "total_spend": 310.25,
        "average_transaction_value": 77.56,
    },
]

GLOBEX_CUSTOMERS: list[dict[str, object]] = [
    {
        "customer_id": "GLOBEX-0001",
        "first_name": "Ingrid",
        "last_name": "Solberg",
        "email": "ingrid.solberg@example.com",
        "city": "Minneapolis",
        "state": "MN",
        "transaction_count": 19,
        "total_spend": 2890.00,
        "average_transaction_value": 152.11,
    },
]

# (email, role, invited_by email, state) where state controls the
# resulting status: "pending" leaves it as-is, "accepted" immediately
# accepts it, "expired" backdates expires_at into the past.
INVITATIONS: list[tuple[str, str, str, str]] = [
    ("new.hire@example.com", "customer_success", "sarah.johnson@example.com", "pending"),
    ("returning.contractor@example.com", "viewer", "sarah.johnson@example.com", "accepted"),
    ("stale.invite@example.com", "operations", "sarah.johnson@example.com", "expired"),
]


@dataclass(frozen=True)
class TenancySeedResult:
    organizations_created: int
    users_created: int
    memberships_created: int
    customers_created: int
    invitations_created: int


def seeding_enabled(*, force: bool = False) -> bool:
    return force or os.getenv("ENABLE_DEMO_SEED", "").strip().lower() == "true"


def _get_or_create_organization(repo: OrganizationRepository, name: str, slug: str) -> tuple[Organization, bool]:
    existing = repo.get_by_slug(slug)
    if existing is not None:
        return existing, False
    return repo.create(name), True


def _get_or_create_user(repo: UserRepository, name: str, email: str, avatar_color: str) -> tuple[User, bool]:
    existing = repo.get_by_email(email)
    if existing is not None:
        return existing, False
    return repo.create(name, email, avatar_color=avatar_color), True


def seed_demo_tenancy(session: Session) -> TenancySeedResult:
    org_repo = OrganizationRepository(session)
    user_repo = UserRepository(session)
    membership_repo = MembershipRepository(session)
    invitation_repo = InvitationRepository(session)
    customer_repo = Customer360Repository(session)

    organizations_created = 0
    for org_spec in ORGANIZATIONS:
        _org, created = _get_or_create_organization(org_repo, org_spec["name"], org_spec["slug"])
        organizations_created += int(created)

    users_created = 0
    for user_spec in USERS:
        _user, created = _get_or_create_user(
            user_repo, user_spec["name"], user_spec["email"], user_spec["avatar_color"]
        )
        users_created += int(created)

    memberships_created = 0
    for email, slug, role in MEMBERSHIPS:
        user = user_repo.get_by_email(email)
        org = org_repo.get_by_slug(slug)
        if user is None or org is None:
            continue
        if membership_repo.get(user.id, org.id) is None:
            membership_repo.create(user.id, org.id, role)
            memberships_created += 1

    customers_created = 0
    acme = org_repo.get_by_slug("acme-corporation")
    globex = org_repo.get_by_slug("globex-corporation")
    for org, records in ((acme, ACME_CUSTOMERS), (globex, GLOBEX_CUSTOMERS)):
        if org is None:
            continue
        for record in records:
            if customer_repo.get_by_customer_id(str(record["customer_id"])) is not None:
                continue
            customer_repo.create(Customer360Profile(**record, organization_id=org.id))
            customers_created += 1

    invitations_created = 0
    sarah = user_repo.get_by_email("sarah.johnson@example.com")
    acme = org_repo.get_by_slug("acme-corporation")
    if sarah is not None and acme is not None:
        existing_emails = {inv.email for inv in invitation_repo.list_for_organization(acme.id)}
        for email, role, _invited_by_email, state in INVITATIONS:
            if email in existing_emails:
                continue
            expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
            if state == "expired":
                expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
            invitation = invitation_repo.create(
                organization_id=acme.id,
                email=email,
                role=role,
                invited_by_user_id=sarah.id,
                expires_at=expires_at,
            )
            if state == "accepted":
                invitation_repo.mark_accepted(invitation)
            invitations_created += 1

    return TenancySeedResult(
        organizations_created=organizations_created,
        users_created=users_created,
        memberships_created=memberships_created,
        customers_created=customers_created,
        invitations_created=invitations_created,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if ENABLE_DEMO_SEED is not set to 'true'.",
    )
    args = parser.parse_args(argv)

    if not seeding_enabled(force=args.force):
        print(
            "Refusing to seed: set ENABLE_DEMO_SEED=true or pass --force.",
            file=sys.stderr,
        )
        return 1

    session = SessionLocal()
    try:
        result = seed_demo_tenancy(session)
    finally:
        session.close()

    print(
        "Seeded demo tenancy: "
        f"{result.organizations_created} organizations, "
        f"{result.users_created} users, "
        f"{result.memberships_created} memberships, "
        f"{result.customers_created} customers, "
        f"{result.invitations_created} invitations created."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
