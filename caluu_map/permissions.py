"""Permission helpers for Caluu Map.

Role model per campus (via :class:`caluu_map.models.CampusContributor`):

* ``viewer``       -- read-only
* ``contributor``  -- can create/update map content on the campus
* ``moderator``    -- can additionally review reports and deactivate content
* ``campus_admin`` -- full management of their campus (incl. contributors)

Superusers may do everything. All write/management permissions are enforced
here on the backend and never left to the frontend.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import CampusContributor


ROLE_LEVEL = {
    "viewer": 0,
    "contributor": 1,
    "moderator": 2,
    "campus_admin": 3,
}

ROLE_VIEWER = 0
ROLE_CONTRIBUTOR = 1
ROLE_MODERATOR = 2
ROLE_CAMPUS_ADMIN = 3


def is_superuser(user):
    return user is not None and not getattr(user, "is_anonymous", True) and user.is_superuser


def active_membership(user, campus):
    """Return the active CampusContributor row for a user+campus, or None."""
    if user is None or getattr(user, "is_anonymous", True):
        return None
    try:
        return CampusContributor.objects.get(user=user, campus=campus, status="active")
    except CampusContributor.DoesNotExist:
        return None


def role_level(user, campus):
    membership = active_membership(user, campus)
    if membership is None:
        return None
    return ROLE_LEVEL.get(membership.role)


def can_manage_campus(user, campus, min_role=ROLE_CONTRIBUTOR):
    """True when the user may modify content on the campus."""
    if is_superuser(user):
        return True
    level = role_level(user, campus)
    return level is not None and level >= min_role


def can_moderate(user, campus):
    """True when the user may approve/reject content on a campus.

    Approvers are campus admins, moderators, or superusers -- matching the
    'campus_admin, moderator, or superuser' approval model the caller chose.
    """
    if is_superuser(user):
        return True
    level = role_level(user, campus)
    return level is not None and level >= ROLE_MODERATOR


def can_manage_campus_objects(user, queryset_or_obj):
    """Check permission against the campus of an object (or queryset)."""
    campus = getattr(queryset_or_obj, "campus", None)
    if campus is None:
        return False
    return can_manage_campus(user, campus)


def allow_when(predicate, message="Permission denied."):
    """Build a BasePermission that passes when ``predicate(request.user)`` is True."""

    class _PredicatePermission(BasePermission):
        def has_permission(self, request, view):
            return bool(predicate(request.user))

        def has_object_permission(self, request, view, obj):
            return bool(predicate(request.user))

    _PredicatePermission.message = message
    _PredicatePermission.__name__ = f"Allow_{predicate.__name__}_Permission"
    return _PredicatePermission


class IsCampusContributor(BasePermission):
    """Object-level: user is an active contributor (or above) for the campus."""

    message = "You must be an active contributor for this campus."

    def has_object_permission(self, request, view, obj):
        return can_manage_campus(request.user, obj.campus, ROLE_CONTRIBUTOR)


class IsCampusModerator(BasePermission):
    """Object-level: user is an active moderator (or above) for the campus."""

    message = "You must be an active moderator for this campus."

    def has_object_permission(self, request, view, obj):
        return can_manage_campus(request.user, obj.campus, ROLE_MODERATOR)


class IsCampusAdmin(BasePermission):
    """Object-level: user is an active campus_admin for the campus, or superuser."""

    message = "Campus admin access required."

    def has_object_permission(self, request, view, obj):
        campus = getattr(obj, "campus", obj)
        return can_manage_campus(request.user, campus, ROLE_CAMPUS_ADMIN)


class IsSuperUser(BasePermission):
    message = "Superuser access required."

    def has_permission(self, request, view):
        return is_superuser(request.user)


class IsReadOnly(BasePermission):
    """Allow any request for safe (GET/HEAD/OPTIONS) methods only."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsAuthenticatedForMapEdit(BasePermission):
    """Require a real (non-anonymous) user for map write/management requests.

    Unlike DRF's stock IsAuthenticated this produces a precise, actionable
    message so the caller can tell "you are not logged in" apart from "you
    lack contributor rights" (the latter is enforced separately in the
    per-campus guards with even more detail).
    """

    message = (
        "You must be logged in to modify map content. No valid Bearer token "
        "was attached to the request, or it is missing/expired. Check that "
        "localStorage contains an 'access_token' and that the Authorization "
        "header is 'Bearer <token>'."
    )

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or getattr(user, "is_anonymous", True):
            return False
        return True