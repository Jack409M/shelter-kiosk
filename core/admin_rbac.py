from __future__ import annotations

from flask import session

ROLE_ORDER = ["admin", "shelter_director", "case_manager", "ra", "staff", "demographics_viewer"]
ALL_STAFF_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra", "demographics_viewer"}
ADMIN_CREATABLE_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra", "demographics_viewer"}
SHELTER_DIRECTOR_CREATABLE_ROLES = {"staff", "case_manager", "ra", "demographics_viewer"}
SHELTER_DIRECTOR_MANAGEABLE_ROLES = {"staff", "case_manager", "ra"}


def current_role() -> str:
    return (session.get("role") or "").strip()


def require_admin_role() -> bool:
    return current_role() == "admin"


def require_admin_or_shelter_director_role() -> bool:
    return current_role() in {"admin", "shelter_director"}


def allowed_roles_to_create() -> set[str]:
    role = current_role()

    if role == "admin":
        return set(ADMIN_CREATABLE_ROLES)

    if role == "shelter_director":
        return set(SHELTER_DIRECTOR_CREATABLE_ROLES)

    return set()


def all_roles() -> set[str]:
    return set(ALL_STAFF_ROLES)


def ordered_roles(role_set) -> list[str]:
    return [role for role in ROLE_ORDER if role in role_set]


def can_manage_target_role(target_role: str) -> bool:
    role = current_role()
    normalized_target_role = (target_role or "").strip()

    if role == "admin":
        return True

    if role == "shelter_director":
        return normalized_target_role in SHELTER_DIRECTOR_MANAGEABLE_ROLES

    return False
