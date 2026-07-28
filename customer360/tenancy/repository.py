from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer360.tenancy.models import ApiKey, Invitation, Membership, Organization, User


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "organization"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str) -> Organization:
        base_slug = _slugify(name)
        slug = base_slug
        suffix = 2
        while self.get_by_slug(slug) is not None:
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        org = Organization(name=name, slug=slug)
        self.session.add(org)
        self.session.commit()
        self.session.refresh(org)
        return org

    def get_by_id(self, organization_id: int) -> Organization | None:
        return self.session.get(Organization, organization_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        statement = select(Organization).where(Organization.slug == slug)
        return self.session.scalar(statement)

    def list_for_user(self, user_id: int) -> list[Organization]:
        statement = (
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.name)
        )
        return list(self.session.scalars(statement))

    def update_branding(
        self,
        organization: Organization,
        *,
        name: str | None = None,
        logo_url: str | None = None,
        theme: str | None = None,
    ) -> Organization:
        if name is not None:
            organization.name = name
        if logo_url is not None:
            organization.logo_url = logo_url
        if theme is not None:
            organization.theme = theme
        self.session.commit()
        self.session.refresh(organization)
        return organization


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str, email: str, *, avatar_color: str = "#3b82f6") -> User:
        user = User(name=name, email=email, avatar_color=avatar_color)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.scalar(statement)

    def list_all(self) -> list[User]:
        statement = select(User).order_by(User.name)
        return list(self.session.scalars(statement))

    def touch_last_login(self, user: User) -> User:
        user.last_login_at = _now()
        self.session.commit()
        self.session.refresh(user)
        return user


class MembershipRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_id: int, organization_id: int, role: str) -> Membership:
        membership = Membership(user_id=user_id, organization_id=organization_id, role=role)
        self.session.add(membership)
        self.session.commit()
        self.session.refresh(membership)
        return membership

    def get_by_id(self, membership_id: int) -> Membership | None:
        return self.session.get(Membership, membership_id)

    def get(self, user_id: int, organization_id: int) -> Membership | None:
        statement = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        return self.session.scalar(statement)

    def list_for_user(self, user_id: int) -> list[Membership]:
        statement = select(Membership).where(Membership.user_id == user_id)
        return list(self.session.scalars(statement))

    def list_members(self, organization_id: int) -> list[tuple[Membership, User]]:
        statement = (
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == organization_id)
            .order_by(User.name)
        )
        return [(membership, user) for membership, user in self.session.execute(statement)]

    def update_role(self, membership: Membership, role: str) -> Membership:
        membership.role = role
        self.session.commit()
        self.session.refresh(membership)
        return membership

    def delete(self, membership: Membership) -> None:
        self.session.delete(membership)
        self.session.commit()


class InvitationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        organization_id: int,
        email: str,
        role: str,
        invited_by_user_id: int | None,
        expires_at: datetime,
    ) -> Invitation:
        invitation = Invitation(
            organization_id=organization_id,
            email=email,
            role=role,
            invited_by_user_id=invited_by_user_id,
            expires_at=expires_at,
        )
        self.session.add(invitation)
        self.session.commit()
        self.session.refresh(invitation)
        return invitation

    def get_by_id(self, invitation_id: int) -> Invitation | None:
        return self.session.get(Invitation, invitation_id)

    def list_for_organization(self, organization_id: int) -> list[Invitation]:
        statement = (
            select(Invitation)
            .where(Invitation.organization_id == organization_id)
            .order_by(Invitation.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def mark_accepted(self, invitation: Invitation) -> Invitation:
        invitation.status = "accepted"
        invitation.accepted_at = _now()
        self.session.commit()
        self.session.refresh(invitation)
        return invitation

    def mark_revoked(self, invitation: Invitation) -> Invitation:
        invitation.status = "revoked"
        self.session.commit()
        self.session.refresh(invitation)
        return invitation


class ApiKeyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, organization_id: int, name: str, key_prefix: str, hashed_key: str
    ) -> ApiKey:
        api_key = ApiKey(
            organization_id=organization_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
        )
        self.session.add(api_key)
        self.session.commit()
        self.session.refresh(api_key)
        return api_key

    def get_by_id(self, api_key_id: int) -> ApiKey | None:
        return self.session.get(ApiKey, api_key_id)

    def get_by_hash(self, hashed_key: str) -> ApiKey | None:
        statement = select(ApiKey).where(ApiKey.hashed_key == hashed_key)
        return self.session.scalar(statement)

    def list_for_organization(self, organization_id: int) -> list[ApiKey]:
        statement = (
            select(ApiKey)
            .where(ApiKey.organization_id == organization_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def mark_used(self, api_key: ApiKey) -> ApiKey:
        api_key.last_used_at = _now()
        self.session.commit()
        self.session.refresh(api_key)
        return api_key

    def rotate(self, api_key: ApiKey, *, key_prefix: str, hashed_key: str) -> ApiKey:
        api_key.key_prefix = key_prefix
        api_key.hashed_key = hashed_key
        api_key.last_used_at = None
        self.session.commit()
        self.session.refresh(api_key)
        return api_key

    def revoke(self, api_key: ApiKey) -> ApiKey:
        api_key.status = "revoked"
        self.session.commit()
        self.session.refresh(api_key)
        return api_key
