"""Multi-tenancy endpoints: demo-tier auth/session, organizations, members,
invitations, and API keys. Split out from main.py to keep that file
manageable; mounted via `app.include_router(tenancy_router)`.

Every route here lives under /demo/api/*, unauthenticated by the same
convention as the rest of that surface (no X-API-Key) -- this is still
the public demo/workspace tier, not the real authenticated /api/v1
surface, which this module never touches.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from customer360.api.rate_limit import limiter
from customer360.infrastructure.session import get_db_session
from customer360.tenancy.models import Invitation
from customer360.tenancy.permissions import Role, has_permission
from customer360.tenancy.repository import (
    ApiKeyRepository,
    InvitationRepository,
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)
from customer360.tenancy.session import SessionContext, get_session_context

router = APIRouter(prefix="/demo/api", tags=["tenancy"], include_in_schema=False)

RoleLiteral = Literal["admin", "operations", "customer_success", "executive", "viewer"]

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ---------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str


class SessionUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    avatar_color: str


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    logo_url: str | None
    theme: str


class SessionResponse(BaseModel):
    user: SessionUserResponse | None = None
    organization: OrganizationResponse | None = None
    role: str | None = None
    available_organizations: list[OrganizationResponse] = Field(default_factory=list)


class DemoUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    avatar_color: str


class LoginRequest(BaseModel):
    user_id: int
    organization_id: int | None = None


class SwitchWorkspaceRequest(BaseModel):
    organization_id: int


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_name: str = Field(min_length=1, max_length=200)
    admin_email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = Field(default=None, max_length=500)
    theme: Literal["dark", "light"] | None = None


class MemberResponse(BaseModel):
    membership_id: int
    user_id: int
    name: str
    email: str
    avatar_color: str
    role: str
    status: str
    last_login_at: datetime | None


class UpdateMembershipRequest(BaseModel):
    role: RoleLiteral


class InviteUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    role: RoleLiteral


class InvitationResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    invited_by: str | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    status: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    full_key: str


class GenerateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class VerifyApiKeyResponse(BaseModel):
    organization_id: int
    organization_name: str
    key_name: str


# ---------------------------------------------------------------------
# Session dependencies
# ---------------------------------------------------------------------


def get_session(
    request: Request, session: Session = Depends(get_db_session)
) -> SessionContext | None:
    return get_session_context(request, session)


def require_session(
    session_context: SessionContext | None = Depends(get_session),
) -> SessionContext:
    if session_context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return session_context


def require_permission(action: str):
    def _dependency(
        session_context: SessionContext = Depends(require_session),
    ) -> SessionContext:
        if not has_permission(session_context.role, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{session_context.role}' cannot perform '{action}'",
            )
        return session_context

    return _dependency


def _session_response(ctx: SessionContext) -> SessionResponse:
    return SessionResponse(
        user=SessionUserResponse(
            id=ctx.user_id,
            name=ctx.user_name,
            email=ctx.user_email,
            avatar_color=ctx.user_avatar_color,
        ),
        organization=OrganizationResponse(
            id=ctx.organization_id,
            name=ctx.organization_name,
            slug=ctx.organization_slug,
            logo_url=ctx.organization_logo_url,
            theme=ctx.organization_theme,
        ),
        role=ctx.role,
    )


def _require_own_organization(ctx: SessionContext, organization_id: int) -> None:
    if ctx.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage a different organization",
        )


# ---------------------------------------------------------------------
# Auth / session
# ---------------------------------------------------------------------


@router.get("/auth/users", response_model=list[DemoUserResponse])
@limiter.limit("60/minute")
def list_demo_users(
    request: Request, session: Session = Depends(get_db_session)
) -> list[DemoUserResponse]:
    users = UserRepository(session).list_all()
    return [DemoUserResponse.model_validate(user) for user in users]


@router.post(
    "/auth/login",
    response_model=SessionResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def login(
    request: Request,
    body: LoginRequest,
    session: Session = Depends(get_db_session),
) -> SessionResponse:
    user_repo = UserRepository(session)
    user = user_repo.get_by_id(body.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    membership_repo = MembershipRepository(session)
    memberships = membership_repo.list_for_user(user.id)
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user has no organization memberships",
        )

    request.session["user_id"] = user.id

    target_org_id: int | None = body.organization_id
    if target_org_id is None and len(memberships) == 1:
        target_org_id = memberships[0].organization_id

    if target_org_id is not None:
        matching = next(
            (m for m in memberships if m.organization_id == target_org_id), None
        )
        if matching is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of that organization",
            )
        request.session["organization_id"] = target_org_id
        user_repo.touch_last_login(user)
        ctx = get_session_context(request, session)
        assert ctx is not None
        return _session_response(ctx)

    request.session.pop("organization_id", None)
    org_repo = OrganizationRepository(session)
    orgs = [
        org
        for m in memberships
        if (org := org_repo.get_by_id(m.organization_id)) is not None
    ]
    return SessionResponse(
        user=SessionUserResponse.model_validate(user),
        available_organizations=[OrganizationResponse.model_validate(o) for o in orgs],
    )


@router.post("/auth/logout")
@limiter.limit("30/minute")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@router.get("/auth/session", response_model=SessionResponse)
@limiter.limit("60/minute")
def read_session(
    request: Request, session: Session = Depends(get_db_session)
) -> SessionResponse:
    user_id = request.session.get("user_id")
    if user_id is None:
        return SessionResponse()

    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        return SessionResponse()

    ctx = get_session_context(request, session)
    if ctx is not None:
        return _session_response(ctx)

    org_repo = OrganizationRepository(session)
    memberships = MembershipRepository(session).list_for_user(user.id)
    orgs = [
        org
        for m in memberships
        if (org := org_repo.get_by_id(m.organization_id)) is not None
    ]
    return SessionResponse(
        user=SessionUserResponse.model_validate(user),
        available_organizations=[OrganizationResponse.model_validate(o) for o in orgs],
    )


@router.post(
    "/auth/switch-workspace",
    response_model=SessionResponse,
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse}},
)
@limiter.limit("30/minute")
def switch_workspace(
    request: Request,
    body: SwitchWorkspaceRequest,
    session: Session = Depends(get_db_session),
) -> SessionResponse:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")

    membership = MembershipRepository(session).get(user_id, body.organization_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of that organization",
        )

    request.session["organization_id"] = body.organization_id
    ctx = get_session_context(request, session)
    assert ctx is not None
    return _session_response(ctx)


# ---------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------


@router.post("/organizations", response_model=SessionResponse)
@limiter.limit("10/minute")
def create_organization(
    request: Request,
    body: CreateOrganizationRequest,
    session: Session = Depends(get_db_session),
) -> SessionResponse:
    user_repo = UserRepository(session)
    if user_repo.get_by_email(body.admin_email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    organization = OrganizationRepository(session).create(body.name)
    admin_user = user_repo.create(body.admin_name, body.admin_email)
    MembershipRepository(session).create(admin_user.id, organization.id, Role.ADMIN.value)

    request.session["user_id"] = admin_user.id
    request.session["organization_id"] = organization.id
    user_repo.touch_last_login(admin_user)

    ctx = get_session_context(request, session)
    assert ctx is not None
    return _session_response(ctx)


@router.get("/organizations", response_model=list[OrganizationResponse])
@limiter.limit("60/minute")
def list_my_organizations(
    request: Request, session: Session = Depends(get_db_session)
) -> list[OrganizationResponse]:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    orgs = OrganizationRepository(session).list_for_user(user_id)
    return [OrganizationResponse.model_validate(o) for o in orgs]


@router.patch(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def update_organization(
    request: Request,
    body: UpdateOrganizationRequest,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> OrganizationResponse:
    _require_own_organization(ctx, organization_id)
    org_repo = OrganizationRepository(session)
    organization = org_repo.get_by_id(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    updated = org_repo.update_branding(
        organization, name=body.name, logo_url=body.logo_url, theme=body.theme
    )
    return OrganizationResponse.model_validate(updated)


# ---------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------


@router.get("/organizations/{organization_id}/members", response_model=list[MemberResponse])
@limiter.limit("60/minute")
def list_members(
    request: Request,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> list[MemberResponse]:
    _require_own_organization(ctx, organization_id)
    rows = MembershipRepository(session).list_members(organization_id)
    return [
        MemberResponse(
            membership_id=membership.id,
            user_id=user.id,
            name=user.name,
            email=user.email,
            avatar_color=user.avatar_color,
            role=membership.role,
            status=user.status,
            last_login_at=user.last_login_at,
        )
        for membership, user in rows
    ]


@router.patch(
    "/memberships/{membership_id}",
    response_model=MemberResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def update_membership_role(
    request: Request,
    body: UpdateMembershipRequest,
    membership_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> MemberResponse:
    membership_repo = MembershipRepository(session)
    membership = membership_repo.get_by_id(membership_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    _require_own_organization(ctx, membership.organization_id)

    updated = membership_repo.update_role(membership, body.role)
    user = UserRepository(session).get_by_id(updated.user_id)
    assert user is not None
    return MemberResponse(
        membership_id=updated.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        avatar_color=user.avatar_color,
        role=updated.role,
        status=user.status,
        last_login_at=user.last_login_at,
    )


@router.delete(
    "/memberships/{membership_id}",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def remove_membership(
    request: Request,
    membership_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> dict[str, bool]:
    membership_repo = MembershipRepository(session)
    membership = membership_repo.get_by_id(membership_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    _require_own_organization(ctx, membership.organization_id)

    membership_repo.delete(membership)
    return {"ok": True}


# ---------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------


def _invitation_response(invitation: Invitation, session: Session) -> InvitationResponse:
    effective_status = invitation.status
    now = datetime.now(UTC).replace(tzinfo=None)
    if effective_status == "pending" and invitation.expires_at < now:
        effective_status = "expired"

    invited_by_name = None
    if invitation.invited_by_user_id is not None:
        inviter = UserRepository(session).get_by_id(invitation.invited_by_user_id)
        invited_by_name = inviter.name if inviter is not None else None

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=effective_status,
        invited_by=invited_by_name,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
    )


@router.get(
    "/organizations/{organization_id}/invitations", response_model=list[InvitationResponse]
)
@limiter.limit("60/minute")
def list_invitations(
    request: Request,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> list[InvitationResponse]:
    _require_own_organization(ctx, organization_id)
    invitations = InvitationRepository(session).list_for_organization(organization_id)
    return [_invitation_response(inv, session) for inv in invitations]


@router.post("/organizations/{organization_id}/invitations", response_model=InvitationResponse)
@limiter.limit("20/minute")
def create_invitation(
    request: Request,
    body: InviteUserRequest,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> InvitationResponse:
    _require_own_organization(ctx, organization_id)
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    invitation = InvitationRepository(session).create(
        organization_id=organization_id,
        email=body.email,
        role=body.role,
        invited_by_user_id=ctx.user_id,
        expires_at=expires_at,
    )
    return _invitation_response(invitation, session)


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=InvitationResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def accept_invitation(
    request: Request,
    invitation_id: int = Path(...),
    session: Session = Depends(get_db_session),
) -> InvitationResponse:
    # Deliberately no require_permission: this is self-service by the
    # invited person. There's no email delivery in this app, so the UI
    # triggers this directly (clearly labeled as simulated acceptance)
    # rather than the invitee clicking a real emailed link.
    invitation_repo = InvitationRepository(session)
    invitation = invitation_repo.get_by_id(invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation is not pending"
        )

    user_repo = UserRepository(session)
    user = user_repo.get_by_email(invitation.email)
    if user is None:
        display_name = invitation.email.split("@", 1)[0].replace(".", " ").title()
        user = user_repo.create(display_name, invitation.email)

    membership_repo = MembershipRepository(session)
    if membership_repo.get(user.id, invitation.organization_id) is None:
        membership_repo.create(user.id, invitation.organization_id, invitation.role)

    updated = invitation_repo.mark_accepted(invitation)
    return _invitation_response(updated, session)


@router.post(
    "/invitations/{invitation_id}/revoke",
    response_model=InvitationResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def revoke_invitation(
    request: Request,
    invitation_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> InvitationResponse:
    invitation_repo = InvitationRepository(session)
    invitation = invitation_repo.get_by_id(invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    _require_own_organization(ctx, invitation.organization_id)

    updated = invitation_repo.mark_revoked(invitation)
    return _invitation_response(updated, session)


# ---------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------


def _hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def _generate_key_material() -> tuple[str, str, str]:
    full_key = f"sk_live_{secrets.token_urlsafe(32)}"
    prefix = full_key[:16] + "…"
    return full_key, prefix, _hash_key(full_key)


@router.get("/organizations/{organization_id}/api-keys", response_model=list[ApiKeyResponse])
@limiter.limit("60/minute")
def list_api_keys(
    request: Request,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> list[ApiKeyResponse]:
    _require_own_organization(ctx, organization_id)
    keys = ApiKeyRepository(session).list_for_organization(organization_id)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.post("/organizations/{organization_id}/api-keys", response_model=ApiKeyCreatedResponse)
@limiter.limit("20/minute")
def generate_api_key(
    request: Request,
    body: GenerateApiKeyRequest,
    organization_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> ApiKeyCreatedResponse:
    _require_own_organization(ctx, organization_id)
    full_key, prefix, hashed = _generate_key_material()
    created = ApiKeyRepository(session).create(
        organization_id=organization_id, name=body.name, key_prefix=prefix, hashed_key=hashed
    )
    return ApiKeyCreatedResponse(
        id=created.id,
        name=created.name,
        key_prefix=created.key_prefix,
        status=created.status,
        created_at=created.created_at,
        last_used_at=created.last_used_at,
        full_key=full_key,
    )


@router.post(
    "/api-keys/{api_key_id}/rotate",
    response_model=ApiKeyCreatedResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def rotate_api_key(
    request: Request,
    api_key_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> ApiKeyCreatedResponse:
    api_key_repo = ApiKeyRepository(session)
    api_key = api_key_repo.get_by_id(api_key_id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    _require_own_organization(ctx, api_key.organization_id)

    full_key, prefix, hashed = _generate_key_material()
    updated = api_key_repo.rotate(api_key, key_prefix=prefix, hashed_key=hashed)
    return ApiKeyCreatedResponse(
        id=updated.id,
        name=updated.name,
        key_prefix=updated.key_prefix,
        status=updated.status,
        created_at=updated.created_at,
        last_used_at=updated.last_used_at,
        full_key=full_key,
    )


@router.post(
    "/api-keys/{api_key_id}/revoke",
    response_model=ApiKeyResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
@limiter.limit("20/minute")
def revoke_api_key(
    request: Request,
    api_key_id: int = Path(...),
    session: Session = Depends(get_db_session),
    ctx: SessionContext = Depends(require_permission("organization.manage")),
) -> ApiKeyResponse:
    api_key_repo = ApiKeyRepository(session)
    api_key = api_key_repo.get_by_id(api_key_id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    _require_own_organization(ctx, api_key.organization_id)

    updated = api_key_repo.revoke(api_key)
    return ApiKeyResponse.model_validate(updated)


@router.post(
    "/api-keys/verify",
    response_model=VerifyApiKeyResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
@limiter.limit("30/minute")
def verify_api_key_route(
    request: Request,
    x_org_api_key: str | None = Header(default=None),
    session: Session = Depends(get_db_session),
) -> VerifyApiKeyResponse:
    if not x_org_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Org-API-Key header"
        )

    api_key_repo = ApiKeyRepository(session)
    api_key = api_key_repo.get_by_hash(_hash_key(x_org_api_key))
    if api_key is None or api_key.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key"
        )

    updated = api_key_repo.mark_used(api_key)
    organization = OrganizationRepository(session).get_by_id(updated.organization_id)
    return VerifyApiKeyResponse(
        organization_id=updated.organization_id,
        organization_name=organization.name if organization is not None else "",
        key_name=updated.name,
    )
