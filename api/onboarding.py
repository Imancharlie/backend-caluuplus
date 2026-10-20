"""Onboarding progress, social proof, and profile completion.

Existing accounts are marked complete by migration so they are not sent
through the new screens. New accounts start with an empty state.
"""
import os
import uuid
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Student, User

INTEREST_CHOICES = [
    "football",
    "basketball",
    "volleyball",
    "netball",
    "athletics",
    "running",
    "gym",
    "yoga",
    "swimming",
    "tennis",
    "cricket",
    "music",
    "singing",
    "dancing",
    "instruments",
    "dj",
    "movies",
    "gaming",
    "esports",
    "chess",
    "board_games",
    "reading",
    "writing",
    "poetry",
    "drawing",
    "photography",
    "acting",
    "fashion",
    "makeup",
    "cooking",
    "baking",
    "travel",
    "hiking",
    "nature",
    "programming",
    "web_development",
    "ai",
    "cybersecurity",
    "robotics",
    "entrepreneurship",
    "business",
    "marketing",
    "investing",
    "leadership",
    "public_speaking",
    "debate",
    "volunteering",
    "faith",
    "science",
    "languages",
    "other",
]
REMINDER_DAYS = 7
PHOTO_REMINDER_DAYS = 5
PHOTO_STATUSES = {"pending", "saved", "skipped", "legacy"}


def read_state(user):
    raw = user.onboarding_state if isinstance(user.onboarding_state, dict) else {}
    status_value = raw.get("interests_status") or "pending"
    photo_status = raw.get("photo_status")
    if photo_status not in PHOTO_STATUSES:
        photo_status = "legacy" if status_value == "legacy" else "pending"
    return {
        "social_seen": bool(raw.get("social_seen")),
        "interests_status": status_value,
        "reminder_after": raw.get("reminder_after"),
        "dismiss_count": int(raw.get("dismiss_count") or 0),
        "photo_status": photo_status,
        "photo_reminder_after": raw.get("photo_reminder_after"),
        "photo_dismiss_count": int(raw.get("photo_dismiss_count") or 0),
        "photo_path": raw.get("photo_path") or "",
        "google_picture": raw.get("google_picture") or "",
    }


def write_state(user, **changes):
    state = read_state(user)
    state.update(changes)
    user.onboarding_state = state
    user.save(update_fields=["onboarding_state"])
    return state


def mark_interests_saved(user):
    if read_state(user)["interests_status"] != "saved":
        write_state(user, interests_status="saved", reminder_after=None)


def photo_is_saved(user):
    return read_state(user)["photo_status"] == "saved"


def mark_photo_saved(user, photo_path):
    write_state(user, photo_status="saved", photo_reminder_after=None, photo_path=photo_path or "")


def assign_firebase_picture(user, picture):
    """Use the Google photo unless the person has uploaded their own.

    A Google photo is the default, and it stays current on later sign-ins.
    An uploaded photo replaces it and is left alone until the person removes it.
    """
    picture = (picture or "").strip()
    if not picture:
        return False
    state = read_state(user)
    if state.get("google_picture") != picture:
        write_state(user, google_picture=picture)
    if photo_is_saved(user) or (user.profile_picture or "").strip() == picture:
        return False
    user.profile_picture = picture
    return True


def _aware(value):
    if not value:
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def photo_prompt_due(user, state):
    if (user.profile_picture or "").strip() or state["photo_status"] == "saved":
        return False
    reminder = _aware(state.get("photo_reminder_after"))
    if reminder is not None:
        return timezone.now() >= reminder
    joined = _aware(user.date_joined) or timezone.now()
    return timezone.now() >= joined + timedelta(days=PHOTO_REMINDER_DAYS)


def _student(user):
    return Student.objects.filter(user=user).select_related("program", "college", "university").first()


def completion_payload(user):
    state = read_state(user)
    student = _student(user)
    interests_done = state["interests_status"] in {"saved", "skipped", "legacy"} or bool(user.hobbies)
    items = [
        {"key": "name", "label": "Name", "done": bool((user.display_name or "").strip()), "optional": False},
        {"key": "academic", "label": "Academic profile", "done": student is not None, "optional": False},
    ]
    if state["interests_status"] not in {"skipped", "legacy"}:
        items.append({
            "key": "interests",
            "label": "Interests",
            "done": bool(user.hobbies),
            "optional": True,
        })
    required = [item for item in items if not item["optional"] or state["interests_status"] == "pending"]
    done_count = sum(1 for item in required if item["done"])
    percent = int(round(100 * done_count / len(required))) if required else 100
    next_step = next((item["key"] for item in required if not item["done"]), None)
    if next_step is None and state["interests_status"] == "skipped":
        next_step = "interests"
    reminder_due = True
    parsed = _aware(state["reminder_after"])
    if parsed is not None:
        reminder_due = timezone.now() >= parsed
    show_card = state["interests_status"] != "legacy" and reminder_due and (
        percent < 100 or state["interests_status"] == "skipped"
    )
    show_photo_prompt = photo_prompt_due(user, state)
    if next_step is None and show_photo_prompt:
        next_step = "photo"
    return {
        "percent": percent,
        "items": items,
        "next_step": next_step,
        "show_card": show_card,
        "show_photo_prompt": show_photo_prompt,
        "interests_done": interests_done,
        "state": state,
    }


def _people(queryset):
    rows = []
    for person in queryset.order_by("-date_joined")[:6]:
        rows.append({
            "id": str(person.id),
            "display_name": person.display_name,
            "profile_picture": person.profile_picture or None,
        })
    return rows


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def social_proof(request):
    user = request.user
    student = _student(user)
    visible = User.objects.filter(is_active=True, public_profile=True).exclude(id=user.id)
    people = []
    match = None
    if student is not None:
        tiers = [
            (visible.filter(student_profile__program=student.program, student_profile__year=student.year), "programme_year"),
            (visible.filter(student_profile__program=student.program), "programme"),
            (visible.filter(student_profile__college=student.college), "college"),
        ]
        for queryset, label in tiers:
            found = _people(queryset)
            if found:
                people = found
                match = label
                break
    students = User.objects.filter(is_active=True, is_student=True)
    platform_count = students.count()
    student_number = None
    if user.is_student and user.date_joined:
        earlier = students.filter(
            Q(date_joined__lt=user.date_joined) | Q(date_joined=user.date_joined, pk__lt=user.pk)
        ).count()
        student_number = earlier + 1
    return Response({
        "people": people,
        "match": match,
        "platform_count": platform_count,
        "student_number": student_number,
    })


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def onboarding_progress(request):
    user = request.user
    if request.method == "PATCH":
        payload = request.data or {}
        changes = {}
        if payload.get("social_seen") is True:
            changes["social_seen"] = True
        if payload.get("interests_status") == "skipped":
            when = timezone.now() + timedelta(days=REMINDER_DAYS)
            changes["interests_status"] = "skipped"
            changes["reminder_after"] = when.isoformat()
        if payload.get("dismiss_reminder") is True:
            state = read_state(user)
            count = state["dismiss_count"] + 1
            when = timezone.now() + timedelta(days=REMINDER_DAYS * count)
            changes["dismiss_count"] = count
            changes["reminder_after"] = when.isoformat()
        if payload.get("photo_status") == "skipped":
            when = timezone.now() + timedelta(days=PHOTO_REMINDER_DAYS)
            changes["photo_status"] = "skipped"
            changes["photo_reminder_after"] = when.isoformat()
        if payload.get("dismiss_photo_reminder") is True:
            state = read_state(user)
            count = state["photo_dismiss_count"] + 1
            when = timezone.now() + timedelta(days=PHOTO_REMINDER_DAYS)
            changes["photo_dismiss_count"] = count
            changes["photo_reminder_after"] = when.isoformat()
        if changes:
            write_state(user, **changes)
    body = completion_payload(user)
    body["interest_choices"] = INTEREST_CHOICES
    return Response(body, status=status.HTTP_200_OK)


def _delete_profile_file(user):
    path = read_state(user).get("photo_path") or ""
    if path and default_storage.exists(path):
        default_storage.delete(path)


def _bust_user_cache(user):
    try:
        from .utils import safe_cache_delete
        safe_cache_delete(f"user_details_{user.id}")
    except Exception:
        pass


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def profile_picture(request):
    """Upload or remove the signed-in user's profile photo."""
    user = request.user
    if request.method == "DELETE":
        _delete_profile_file(user)
        google_picture = read_state(user).get("google_picture") or ""
        user.profile_picture = google_picture or None
        user.save(update_fields=["profile_picture"])
        when = None if google_picture else (timezone.now() + timedelta(days=PHOTO_REMINDER_DAYS)).isoformat()
        write_state(
            user,
            photo_status="skipped",
            photo_path="",
            photo_reminder_after=when,
        )
        _bust_user_cache(user)
        return Response({"profile_picture": google_picture or None}, status=status.HTTP_200_OK)

    upload = request.FILES.get("image") or request.FILES.get("profile_picture")
    if upload is None:
        return Response({"error": "Choose a photo."}, status=status.HTTP_400_BAD_REQUEST)
    from .community import _validate_image
    image_error = _validate_image(upload)
    if image_error:
        return Response({"error": image_error}, status=status.HTTP_400_BAD_REQUEST)

    _delete_profile_file(user)
    ext = os.path.splitext(upload.name or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".jpg"
    stored = default_storage.save(f"profiles/{user.id}/{uuid.uuid4().hex}{ext}", upload)
    url = request.build_absolute_uri(default_storage.url(stored))
    user.profile_picture = url
    user.save(update_fields=["profile_picture"])
    mark_photo_saved(user, stored)
    _bust_user_cache(user)
    return Response({"profile_picture": url}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def public_user_count(request):
    """Public active-account count for the landing page. No other user data."""
    return Response({"user_count": User.objects.filter(is_active=True).count()})
