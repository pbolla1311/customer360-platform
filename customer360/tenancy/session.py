"""Demo-tier session context: who a Workspace visitor is signed in as, and
which organization/role they're currently acting under.

Backed by Starlette's built-in `SessionMiddleware` (an HMAC-signed cookie
storing only `user_id`/`organization_id` -- no server-side session store).
Role/name lookups are re-read from the database on every request rather
than cached in the cookie, so an admin changing someone's role takes
effect on their very next request, not after they sign in again.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from customer360.tenancy.repository import (
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)


@dataclass(frozen=True)
class SessionContext:
    user_id: int
    user_name: str
    user_email: str
    user_avatar_color: str
    organization_id: int
    organization_name: str
    organization_slug: str
    organization_logo_url: str | None
    organization_theme: str
    role: str


def get_session_context(request: Request, db_session: Session) -> SessionContext | None:
    user_id = request.session.get("user_id")
    organization_id = request.session.get("organization_id")

    if user_id is None or organization_id is None:
        return None

    user = UserRepository(db_session).get_by_id(user_id)
    if user is None:
        return None

    membership = MembershipRepository(db_session).get(user_id, organization_id)
    if membership is None:
        return None

    organization = OrganizationRepository(db_session).get_by_id(organization_id)
    if organization is None:
        return None

    return SessionContext(
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        user_avatar_color=user.avatar_color,
        organization_id=organization.id,
        organization_name=organization.name,
        organization_slug=organization.slug,
        organization_logo_url=organization.logo_url,
        organization_theme=organization.theme,
        role=membership.role,
    )
