"""Single source of truth for user feature permissions."""
import json
import logging
from collections.abc import Iterable


logger = logging.getLogger(__name__)

PERMISSION_KEYS = (
    "workbench.view",
    "absence.create",
    "adjustment.confirm",
    "manual_arrangement.manage",
    "records.view",
    "records.manage",
    "statistics.view",
    "exports.download",
    "timetable.upload",
    "timetable.manage",
)
ALL_PERMISSIONS = PERMISSION_KEYS
DEFAULT_USER_PERMISSIONS = (
    "workbench.view",
    "absence.create",
    "adjustment.confirm",
    "records.view",
)

_PREREQUISITES = {
    "absence.create": "workbench.view",
    "adjustment.confirm": "workbench.view",
    "manual_arrangement.manage": "workbench.view",
    "records.manage": "records.view",
}


def validate_permissions(permissions: Iterable[str]) -> list[str]:
    """Validate and return permissions in stable UI/API order."""
    if isinstance(permissions, (str, bytes)):
        raise ValueError("permissions 必須是字串陣列")
    try:
        values = list(permissions)
    except TypeError as exc:
        raise ValueError("permissions 必須是字串陣列") from exc
    if any(not isinstance(value, str) for value in values):
        raise ValueError("permissions 只可包含字串")

    selected = set(values)
    unknown = selected.difference(PERMISSION_KEYS)
    if unknown:
        raise ValueError(f"未知權限：{', '.join(sorted(unknown))}")

    missing = [
        prerequisite
        for permission, prerequisite in _PREREQUISITES.items()
        if permission in selected and prerequisite not in selected
    ]
    if missing:
        raise ValueError(f"缺少必要權限：{', '.join(sorted(set(missing)))}")
    return [permission for permission in PERMISSION_KEYS if permission in selected]


def serialize_permissions(permissions: Iterable[str]) -> str:
    return json.dumps(validate_permissions(permissions), ensure_ascii=False)


def get_user_permissions(user) -> list[str]:
    """Resolve effective permissions; malformed stored data fails closed."""
    if getattr(user, "role", None) in ("admin", "super_admin"):
        return list(ALL_PERMISSIONS)

    raw = getattr(user, "permissions", None)
    if raw is None:
        return list(DEFAULT_USER_PERMISSIONS)

    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(decoded, list):
            raise ValueError("stored permissions are not an array")
        return validate_permissions(decoded)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.error(
            "Invalid permissions for user %r (id=%r): %s",
            getattr(user, "username", None),
            getattr(user, "id", None),
            exc,
        )
        return []


def user_has_permission(user, permission: str) -> bool:
    return permission in get_user_permissions(user)


def user_has_any_permission(user, permissions: Iterable[str]) -> bool:
    granted = set(get_user_permissions(user))
    return any(permission in granted for permission in permissions)
