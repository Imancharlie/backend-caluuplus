from rest_framework.permissions import BasePermission


def user_is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def user_is_ambassador(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    # Lazy import to avoid circular reference
    from .models import UniversityAmbassador
    return UniversityAmbassador.objects.filter(user=user).exists()


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return user_is_admin(request.user)


class IsAmbassador(BasePermission):
    def has_permission(self, request, view):
        return user_is_ambassador(request.user)




















