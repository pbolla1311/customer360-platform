"""Fixed role/permission model for the Workspace's demo-tier multi-tenancy.

Roles are a closed set (the product doesn't support custom roles), so
they're a StrEnum + permission-set mapping here rather than a database
table -- there is nothing for a table to store beyond what's already
expressed in code, and this keeps role checks a pure, easily-tested
function instead of a query.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    OPERATIONS = "operations"
    CUSTOMER_SUCCESS = "customer_success"
    EXECUTIVE = "executive"
    VIEWER = "viewer"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Admin",
    Role.OPERATIONS: "Operations",
    Role.CUSTOMER_SUCCESS: "Customer Success",
    Role.EXECUTIVE: "Executive",
    Role.VIEWER: "Viewer",
}

# Which roles may even navigate to a given workspace view. Enforced
# primarily client-side (hides the nav item); this mapping is the single
# source of truth the frontend mirrors.
NAV_PERMISSIONS: dict[str, set[Role]] = {
    "overview": {Role.ADMIN, Role.OPERATIONS, Role.CUSTOMER_SUCCESS, Role.EXECUTIVE, Role.VIEWER},
    "customers": {Role.ADMIN, Role.CUSTOMER_SUCCESS, Role.VIEWER},
    "events": {Role.ADMIN, Role.OPERATIONS, Role.CUSTOMER_SUCCESS, Role.VIEWER},
    "pipeline": {Role.ADMIN, Role.OPERATIONS, Role.VIEWER},
    "monitoring": {Role.ADMIN, Role.OPERATIONS, Role.VIEWER},
    "analytics": {Role.ADMIN, Role.EXECUTIVE, Role.VIEWER},
    "audit": {Role.ADMIN, Role.OPERATIONS, Role.CUSTOMER_SUCCESS, Role.EXECUTIVE, Role.VIEWER},
    "api-explorer": {Role.ADMIN},
    "settings": {Role.ADMIN},
}

# Privileged actions, enforced server-side (403 if the session's role
# isn't in the set) regardless of what the client shows/hides.
CAN_EDIT_CUSTOMERS: set[Role] = {Role.ADMIN, Role.CUSTOMER_SUCCESS}
CAN_OPERATE_PIPELINE: set[Role] = {Role.ADMIN, Role.OPERATIONS}
CAN_MANAGE_ORG: set[Role] = {Role.ADMIN}

ACTIONS: dict[str, set[Role]] = {
    "customers.edit": CAN_EDIT_CUSTOMERS,
    "pipeline.operate": CAN_OPERATE_PIPELINE,
    "organization.manage": CAN_MANAGE_ORG,
}


def has_permission(role: str | Role | None, action: str) -> bool:
    """True iff `role` is allowed to perform `action`. A missing/unknown
    role or action fails closed (False), never open."""

    if role is None:
        return False
    try:
        role_enum = Role(role)
    except ValueError:
        return False
    allowed = ACTIONS.get(action)
    if allowed is None:
        return False
    return role_enum in allowed


def can_view(role: str | Role | None, view: str) -> bool:
    if role is None:
        return False
    try:
        role_enum = Role(role)
    except ValueError:
        return False
    allowed = NAV_PERMISSIONS.get(view)
    if allowed is None:
        return False
    return role_enum in allowed
