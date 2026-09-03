from typing import Any, Iterable, Optional, Set
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fail-open cache helpers – Redis outages must never cause 500 errors.
# Every helper catches ``ConnectionInterrupted`` / ``ConnectionError`` and
# returns the caller-supplied default so the rest of the view can proceed
# without caching.
# ---------------------------------------------------------------------------

def safe_cache_get(key: str, default: Any = None, **kwargs) -> Any:
    """Get from Django cache; return *default* on any connection error."""
    try:
        from django.core.cache import cache
        return cache.get(key, default=default, **kwargs)
    except Exception:
        logger.debug("cache.get failed for key=%s – falling back to default", key)
        return default


def safe_cache_set(key: str, value: Any, timeout: Optional[int] = None, **kwargs) -> bool:
    """Set in Django cache; silently ignore connection errors."""
    try:
        from django.core.cache import cache
        if timeout is not None:
            cache.set(key, value, timeout=timeout, **kwargs)
        else:
            cache.set(key, value, **kwargs)
        return True
    except Exception:
        logger.debug("cache.set failed for key=%s – ignoring", key)
        return False


def safe_cache_delete(key: str, **kwargs) -> bool:
    """Delete from Django cache; silently ignore connection errors."""
    try:
        from django.core.cache import cache
        cache.delete(key, **kwargs)
        return True
    except Exception:
        logger.debug("cache.delete failed for key=%s – ignoring", key)
        return False


# ---------------------------------------------------------------------------
# University permission helpers
# ---------------------------------------------------------------------------

def get_allowed_university_ids_for_user(user) -> Set:
    """Return a set of university IDs the user can access.
    Admins: all (None means no restriction); Ambassadors: mapped set; Others: empty set.
    """
    if not user or not user.is_authenticated:
        return set()
    from .models import University, UniversityAmbassador
    if user.is_superuser or user.is_staff:
        # Signal no restriction by returning all IDs as a set for consistency
        return set(University.objects.values_list('id', flat=True))
    amb_ids = UniversityAmbassador.objects.filter(user=user).values_list('university_id', flat=True)
    return set(amb_ids)


def restrict_queryset_to_user_universities(queryset, user):
    """Apply university scope by model type.
    Expects models to be one of University/College/Program/Course/Student.
    """
    allowed = get_allowed_university_ids_for_user(user)
    if not allowed:
        # If user has no scope (and not admin), return empty
        if not (user and user.is_authenticated and (user.is_superuser or user.is_staff)):
            return queryset.none()
    model_name = queryset.model.__name__
    if model_name == 'University':
        return queryset.filter(id__in=allowed) if allowed else queryset
    if model_name == 'College':
        return queryset.select_related('university').filter(university_id__in=allowed) if allowed else queryset
    if model_name == 'Program':
        return queryset.select_related('college__university').filter(college__university_id__in=allowed) if allowed else queryset
    if model_name == 'Course':
        return queryset.select_related('program__college__university').filter(program__college__university_id__in=allowed) if allowed else queryset
    if model_name == 'Student':
        return queryset.select_related('university').filter(university_id__in=allowed) if allowed else queryset
    return queryset


def assert_user_can_modify_related_university(user, *, university=None, college=None, program=None):
    """Ensure the user can modify the resource tied to the given relation chain.
    Raises PermissionError if outside scope for ambassadors.
    Admins are allowed.
    """
    if not user or not user.is_authenticated:
        raise PermissionError('Authentication required')
    if user.is_superuser or user.is_staff:
        return
    # Determine target university
    if university is None:
        if college is not None:
            university = college.university
        elif program is not None:
            college = program.college
            university = college.university
    if university is None:
        raise PermissionError('Unable to resolve target university for permission check')
    allowed = get_allowed_university_ids_for_user(user)
    if str(university.id) not in {str(u) for u in allowed}:
        raise PermissionError('You are not allowed to modify resources outside your university scope')




















