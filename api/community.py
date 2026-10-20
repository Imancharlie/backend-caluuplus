"""
Stories & Community API.

Endpoints (all require authentication, mounted under /api/):

    GET, POST   /community/stories/
    GET, PATCH, DELETE  /community/stories/<share_code>/
    GET, POST   /community/stories/<share_code>/responses/
    POST        /community/stories/<share_code>/appreciate/
    POST        /community/stories/<share_code>/report/

Photos leave the active row 24 hours after publication and the row plus
image stay on the server until 48 hours have passed. Questions, learned
cards, and competitions stay until archived or removed. Hidden comments are
visible to their author and to the story author. Competition answers are
omitted from responses until the server-side reveal rules allow them.
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    CommunityAppreciation,
    CommunityReport,
    CommunityResponse,
    CommunityStory,
    Notification,
    Student,
    User,
)
from .utils import safe_cache_get, safe_cache_set
from .views import notify_admin_users

PUBLIC_WEB_ORIGIN = "https://caluu.kodin.co.tz"
PHOTO_TTL = timedelta(hours=24)
PHOTO_KEEP = timedelta(days=2)
LEARNED_LIMIT = 400
TITLE_LIMIT = 180
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
PARTICIPATION_MILESTONES = {1, 5, 10, 25}


class StoryWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[c[0] for c in CommunityStory.KIND_CHOICES])
    title = serializers.CharField(max_length=LEARNED_LIMIT, required=False, allow_blank=True)
    body = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    campus_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    card_color = serializers.ChoiceField(
        choices=['pink', 'green', 'navy', 'grey', 'purple'],
        required=False,
        allow_blank=True,
    )
    competition_format = serializers.ChoiceField(
        choices=[c[0] for c in CommunityStory.FORMAT_CHOICES],
        required=False,
        allow_blank=True,
    )
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reveal_at = serializers.DateTimeField(required=False, allow_null=True)
    correct_answer = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    explanation = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    allow_multiple = serializers.BooleanField(required=False, default=False)
    comments_hidden = serializers.BooleanField(required=False, default=False)


class StoryPatchSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=LEARNED_LIMIT, required=False, allow_blank=True)
    body = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    campus_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=[CommunityStory.STATUS_ACTIVE, CommunityStory.STATUS_ARCHIVED],
        required=False,
    )
    competition_format = serializers.ChoiceField(
        choices=[c[0] for c in CommunityStory.FORMAT_CHOICES],
        required=False,
        allow_blank=True,
    )
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reveal_at = serializers.DateTimeField(required=False, allow_null=True)
    correct_answer = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    explanation = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    allow_multiple = serializers.BooleanField(required=False)


class ResponseWriteSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    is_submission = serializers.BooleanField(required=False)


def _request_data(request, fields):
    text_fields = {"title", "body", "campus_name", "card_color", "correct_answer", "explanation", "competition_format"}
    data = {}
    for key in fields:
        if key not in request.data:
            continue
        value = request.data.get(key)
        if isinstance(value, str) and value.strip() == "":
            if key in text_fields:
                data[key] = ""
            continue
        data[key] = value
    return data


def _rate_limit(request, bucket, max_calls, window):
    user_id = getattr(request.user, "id", "anonymous")
    cache_key = f"community_rl_{bucket}_{user_id}"
    current = safe_cache_get(cache_key, 0) or 0
    if current >= max_calls:
        return Response(
            {"error": "Too many requests. Please wait a moment and try again."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    safe_cache_set(cache_key, current + 1, timeout=window)
    return None


def _new_share_code():
    for _ in range(6):
        code = secrets.token_urlsafe(6)
        if not CommunityStory.objects.filter(share_code=code).exists():
            return code
    return secrets.token_urlsafe(9)


def _student_university(user):
    try:
        profile = user.student_profile
    except Student.DoesNotExist:
        return None
    return profile.university


def _creator_payload(user):
    university_name = ""
    try:
        university = user.student_profile.university
        university_name = university.name if university else ""
    except Student.DoesNotExist:
        university_name = ""
    return {
        "id": str(user.id),
        "display_name": user.display_name or user.username or "Student",
        "profile_picture": user.profile_picture or "",
        "university_name": university_name,
    }


def _image_url(request, story):
    if not story.image:
        return None
    try:
        url = story.image.url
    except ValueError:
        return None
    if request is None:
        return url
    return request.build_absolute_uri(url)


def _is_staff(user):
    return bool(user and (user.is_staff or user.is_superuser))


def answers_revealed(story, now=None):
    if story.kind != CommunityStory.KIND_COMPETITION:
        return True
    fmt = story.competition_format or CommunityStory.FORMAT_OPEN
    if fmt == CommunityStory.FORMAT_OPEN:
        return True
    now = now or timezone.now()
    if fmt == CommunityStory.FORMAT_SCHEDULED:
        return bool(story.reveal_at and now >= story.reveal_at)
    if story.reveal_at and now >= story.reveal_at:
        return True
    if fmt in (CommunityStory.FORMAT_DEADLINE, CommunityStory.FORMAT_QUIZ) and story.ends_at:
        return now >= story.ends_at
    return False


def competition_closed(story, now=None):
    if story.kind != CommunityStory.KIND_COMPETITION or not story.ends_at:
        return False
    now = now or timezone.now()
    return now >= story.ends_at


def story_is_active(story, now=None):
    if story.status != CommunityStory.STATUS_ACTIVE:
        return False
    if story.kind == CommunityStory.KIND_PHOTO:
        now = now or timezone.now()
        return bool(story.expires_at and story.expires_at > now)
    return True


def _share_url(story):
    return f"{PUBLIC_WEB_ORIGIN}/stories/{story.share_code}"


def _can_see_secrets(story, user, now=None):
    if _is_staff(user) or story.creator_id == user.id:
        return True
    return answers_revealed(story, now)


def serialize_story(story, request, *, detail=False):
    user = request.user
    now = timezone.now()
    revealed = answers_revealed(story, now)
    see_secrets = _can_see_secrets(story, user, now)
    appreciated = bool(getattr(story, "my_appreciations", None))
    if not hasattr(story, "my_appreciations"):
        appreciated = CommunityAppreciation.objects.filter(story=story, user=user).exists()
    my_submissions = getattr(story, "my_submissions", None)
    if my_submissions is None and detail:
        my_submissions = list(
            story.responses.filter(user=user, is_submission=True).order_by("created_at")
        )
    participant_count = getattr(story, "participant_count", None)
    if participant_count is None and story.kind == CommunityStory.KIND_COMPETITION:
        participant_count = (
            story.responses.filter(is_submission=True).values("user_id").distinct().count()
        )

    payload = {
        "share_code": story.share_code,
        "kind": story.kind,
        "status": story.status,
        "title": story.title,
        "body": story.body,
        "image_url": _image_url(request, story),
        "campus_name": story.campus_name,
        "card_color": story.card_color or "navy",
        "university_name": story.university.name if story.university_id else "",
        "published_at": story.published_at.isoformat(),
        "expires_at": story.expires_at.isoformat() if story.expires_at else None,
        "comments_hidden": bool(story.comments_hidden),
        "is_active_story": story_is_active(story, now),
        "appreciation_count": story.appreciation_count,
        "appreciated": appreciated,
        "response_count": story.response_count,
        "creator": _creator_payload(story.creator),
        "is_creator": story.creator_id == user.id,
        "share_path": f"/stories/{story.share_code}",
        "share_url": _share_url(story),
        "competition": None,
    }
    if story.kind == CommunityStory.KIND_COMPETITION:
        my_submission = None
        if my_submissions:
            first = my_submissions[0]
            my_submission = {
                "id": str(first.id),
                "body": first.body,
                "created_at": first.created_at.isoformat(),
                "score": first.score if see_secrets else None,
            }
        competition = {
            "format": story.competition_format or CommunityStory.FORMAT_OPEN,
            "starts_at": story.starts_at.isoformat() if story.starts_at else None,
            "ends_at": story.ends_at.isoformat() if story.ends_at else None,
            "reveal_at": story.reveal_at.isoformat() if story.reveal_at else None,
            "answers_revealed": revealed,
            "closed": competition_closed(story, now),
            "allow_multiple": story.allow_multiple,
            "participant_count": participant_count or 0,
            "my_submission": my_submission,
            "viewer_can_see_hidden": see_secrets and not revealed,
        }
        if see_secrets:
            competition["correct_answer"] = story.correct_answer
            competition["explanation"] = story.explanation
        payload["competition"] = competition
    return payload


def _base_queryset(user):
    return (
        CommunityStory.objects.select_related(
            "creator",
            "creator__student_profile",
            "creator__student_profile__university",
            "university",
        )
        .prefetch_related(
            Prefetch(
                "appreciations",
                queryset=CommunityAppreciation.objects.filter(user=user),
                to_attr="my_appreciations",
            ),
            Prefetch(
                "responses",
                queryset=CommunityResponse.objects.filter(user=user, is_submission=True).order_by(
                    "created_at"
                ),
                to_attr="my_submissions",
            ),
        )
        .annotate(
            participant_count=Count(
                "responses__user",
                filter=Q(responses__is_submission=True),
                distinct=True,
            )
        )
    )


def active_story_queryset(user):
    now = timezone.now()
    return (
        _base_queryset(user)
        .filter(status=CommunityStory.STATUS_ACTIVE)
        .exclude(Q(kind=CommunityStory.KIND_PHOTO) & (Q(expires_at__lte=now) | Q(expires_at__isnull=True)))
        .annotate(
            story_rank=Case(
                When(kind=CommunityStory.KIND_COMPETITION, ends_at__isnull=True, then=Value(0)),
                When(kind=CommunityStory.KIND_COMPETITION, ends_at__gt=now, then=Value(0)),
                When(kind=CommunityStory.KIND_PHOTO, then=Value(1)),
                When(kind=CommunityStory.KIND_QUESTION, then=Value(2)),
                When(kind=CommunityStory.KIND_LEARNED, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("story_rank", "-published_at")
    )


def purge_kept_photos(now=None):
    """Delete campus photos, and their image files, after they have been stored for two days."""
    now = now or timezone.now()
    cutoff = now - PHOTO_KEEP
    stale = CommunityStory.objects.filter(kind=CommunityStory.KIND_PHOTO).filter(
        Q(purge_at__lte=now) | Q(purge_at__isnull=True, published_at__lte=cutoff)
    )
    for story in stale.iterator():
        image = story.image
        storage = image.storage if image else None
        name = image.name if image else ""
        story.delete()
        if storage and name:
            storage.delete(name)


def _get_visible_story(share_code, user):
    purge_kept_photos()
    story = _base_queryset(user).filter(share_code=share_code).first()
    if story is None:
        return None
    if story.status == CommunityStory.STATUS_REMOVED and not _is_staff(user):
        return None
    return story


def _validate_image(upload):
    if upload is None:
        return None
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        return "Use a JPEG, PNG, WEBP, or GIF image."
    if upload.size > MAX_IMAGE_BYTES:
        return "Images must be 5 MB or smaller."
    ext = os.path.splitext(upload.name or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return "Use a JPEG, PNG, WEBP, or GIF image."
    try:
        from io import BytesIO
        from PIL import Image

        upload.seek(0)
        raw = upload.read()
        upload.seek(0)
        image = Image.open(BytesIO(raw))
        image.verify()
    except Exception:
        return "That file could not be read as an image."
    return None


def _notify(user, title, body, link):
    if user is None:
        return
    Notification.objects.create(
        user=user,
        title=title[:200],
        body=body,
        notification_type="info",
        link=link,
    )


def _submission_recipients(story):
    ids = (
        CommunityResponse.objects.filter(story=story, is_submission=True)
        .exclude(user_id=story.creator_id)
        .values_list("user_id", flat=True)
        .distinct()
    )
    return User.objects.filter(id__in=list(ids))


def notify_due_community_events(force=False):
    """Create deadline and result notifications once. Safe to call from reads."""
    if not force and safe_cache_get("community_due_check"):
        return 0
    if not force:
        safe_cache_set("community_due_check", 1, timeout=60)

    now = timezone.now()
    due = CommunityStory.objects.filter(kind=CommunityStory.KIND_COMPETITION).exclude(
        status=CommunityStory.STATUS_REMOVED
    ).filter(
        Q(deadline_notified=False, ends_at__isnull=False, ends_at__lte=now)
        | Q(results_notified=False, reveal_at__isnull=False, reveal_at__lte=now)
        | Q(
            results_notified=False,
            competition_format__in=[CommunityStory.FORMAT_DEADLINE, CommunityStory.FORMAT_QUIZ],
            ends_at__isnull=False,
            ends_at__lte=now,
            reveal_at__isnull=True,
        )
    )
    sent = 0
    for story in due.select_related("creator"):
        link = f"/stories/{story.share_code}"
        update_fields = []
        if story.ends_at and story.ends_at <= now and not story.deadline_notified:
            _notify(
                story.creator,
                "Your challenge has closed",
                f'"{story.title}" is no longer accepting submissions.',
                link,
            )
            sent += 1
            for participant in _submission_recipients(story):
                _notify(
                    participant,
                    "Challenge deadline reached",
                    f'Submissions for "{story.title}" are now closed.',
                    link,
                )
                sent += 1
            story.deadline_notified = True
            update_fields.append("deadline_notified")
        if (
            story.competition_format != CommunityStory.FORMAT_OPEN
            and answers_revealed(story, now)
            and not story.results_notified
        ):
            _notify(
                story.creator,
                "Challenge results are available",
                f'Results for "{story.title}" can now be viewed.',
                link,
            )
            sent += 1
            for participant in _submission_recipients(story):
                _notify(
                    participant,
                    "Challenge results are available",
                    f'Answers and results for "{story.title}" are ready.',
                    link,
                )
                sent += 1
            story.results_notified = True
            update_fields.append("results_notified")
        if update_fields:
            story.save(update_fields=update_fields)
    return sent


def _apply_competition_fields(story, data, *, creating):
    fmt = data.get("competition_format") or story.competition_format or CommunityStory.FORMAT_OPEN
    if creating and story.kind == CommunityStory.KIND_COMPETITION and not data.get("competition_format"):
        fmt = CommunityStory.FORMAT_OPEN
    if story.kind == CommunityStory.KIND_COMPETITION:
        story.competition_format = fmt
        if "starts_at" in data:
            story.starts_at = data.get("starts_at")
        if "ends_at" in data:
            story.ends_at = data.get("ends_at")
        if "reveal_at" in data:
            story.reveal_at = data.get("reveal_at")
        if "correct_answer" in data and data.get("correct_answer") is not None:
            story.correct_answer = data.get("correct_answer") or ""
        if "explanation" in data and data.get("explanation") is not None:
            story.explanation = data.get("explanation") or ""
        if "allow_multiple" in data and data.get("allow_multiple") is not None:
            story.allow_multiple = bool(data.get("allow_multiple"))
        if fmt == CommunityStory.FORMAT_SCHEDULED and not story.reveal_at:
            raise serializers.ValidationError({"reveal_at": "Choose when answers should be revealed."})
        if fmt == CommunityStory.FORMAT_DEADLINE and not story.ends_at:
            raise serializers.ValidationError({"ends_at": "A deadline competition needs an end time."})
        if story.starts_at and story.ends_at and story.ends_at <= story.starts_at:
            raise serializers.ValidationError({"ends_at": "The end time must be after the start time."})
    else:
        story.competition_format = ""
        story.starts_at = None
        story.ends_at = None
        story.reveal_at = None
        story.correct_answer = ""
        story.explanation = ""
        story.allow_multiple = False


def _readable_validation(exc):
    detail = exc.detail
    if isinstance(detail, dict):
        first = next(iter(detail.values()))
        if isinstance(first, (list, tuple)):
            return str(first[0])
        return str(first)
    if isinstance(detail, list) and detail:
        return str(detail[0])
    return "Check the form and try again."


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def story_list(request):
    if request.method == "GET":
        purge_kept_photos()
        notify_due_community_events()
        try:
            page = max(int(request.GET.get("page", 1)), 1)
        except ValueError:
            page = 1
        try:
            page_size = int(request.GET.get("page_size", 12))
        except ValueError:
            page_size = 12
        page_size = min(max(page_size, 1), 30)
        stories = active_story_queryset(request.user)
        paginator = Paginator(stories, page_size)
        current = paginator.get_page(page)
        return Response(
            {
                "count": paginator.count,
                "page": current.number,
                "page_size": page_size,
                "next": current.next_page_number() if current.has_next() else None,
                "results": [serialize_story(story, request) for story in current.object_list],
            }
        )

    limited = _rate_limit(request, "create", 8, 3600)
    if limited:
        return limited

    fields = [
        "kind",
        "title",
        "body",
        "campus_name",
        "card_color",
        "competition_format",
        "starts_at",
        "ends_at",
        "reveal_at",
        "correct_answer",
        "explanation",
        "allow_multiple",
        "comments_hidden",
    ]
    serializer = StoryWriteSerializer(data=_request_data(request, fields))
    if not serializer.is_valid():
        return Response(
            {"error": "Check the form and try again.", "fields": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    data = serializer.validated_data
    kind = data["kind"]
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    image = request.FILES.get("image")
    image_error = _validate_image(image) if image else None
    if image_error:
        return Response({"error": image_error}, status=status.HTTP_400_BAD_REQUEST)
    if kind == CommunityStory.KIND_PHOTO:
        if image is None:
            return Response({"error": "Choose a photo to share."}, status=status.HTTP_400_BAD_REQUEST)
        if not title:
            title = (body[:80] or "Campus moment").strip()
    elif kind == CommunityStory.KIND_LEARNED:
        text = title or body
        if not text:
            return Response({"error": "Write what you learned today."}, status=status.HTTP_400_BAD_REQUEST)
        if len(text) > LEARNED_LIMIT:
            return Response({"error": f"Keep what you learned to {LEARNED_LIMIT} characters."}, status=status.HTTP_400_BAD_REQUEST)
        title = text
        body = ""
    elif kind == CommunityStory.KIND_QUESTION:
        if len(title) < 3:
            return Response({"error": "Add a question of at least a few words."}, status=status.HTTP_400_BAD_REQUEST)
        if len(title) > TITLE_LIMIT:
            return Response({"error": f"Keep the question to {TITLE_LIMIT} characters."}, status=status.HTTP_400_BAD_REQUEST)
    elif kind == CommunityStory.KIND_COMPETITION:
        if len(title) < 3:
            return Response({"error": "Give the challenge a title."}, status=status.HTTP_400_BAD_REQUEST)
        if len(title) > TITLE_LIMIT:
            return Response({"error": f"Keep the title to {TITLE_LIMIT} characters."}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    story = CommunityStory(
        share_code=_new_share_code(),
        kind=kind,
        creator=request.user,
        university=_student_university(request.user),
        campus_name=(data.get("campus_name") or "").strip(),
        card_color=(data.get("card_color") or "navy") if (data.get("card_color") or "navy") in {"pink", "green", "navy", "grey", "purple"} else "navy",
        title=title[:LEARNED_LIMIT if kind == CommunityStory.KIND_LEARNED else TITLE_LIMIT],
        body=body,
        published_at=now,
        expires_at=(now + PHOTO_TTL) if kind == CommunityStory.KIND_PHOTO else None,
        purge_at=(now + PHOTO_KEEP) if kind == CommunityStory.KIND_PHOTO else None,
        comments_hidden=bool(data.get("comments_hidden")) if kind == CommunityStory.KIND_LEARNED else False,
    )
    if image:
        story.image = image
    try:
        _apply_competition_fields(story, data, creating=True)
    except serializers.ValidationError as exc:
        return Response({"error": _readable_validation(exc)}, status=status.HTTP_400_BAD_REQUEST)
    story.save()
    story = _base_queryset(request.user).get(pk=story.pk)
    return Response(serialize_story(story, request, detail=True), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def story_detail(request, share_code):
    notify_due_community_events()
    story = _get_visible_story(share_code, request.user)
    if story is None:
        return Response({"error": "This story is not available."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(serialize_story(story, request, detail=True))

    if story.creator_id != request.user.id and not _is_staff(request.user):
        return Response({"error": "You can only change your own stories."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "DELETE":
        story.status = CommunityStory.STATUS_REMOVED
        story.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    fields = [
        "title",
        "body",
        "campus_name",
        "status",
        "competition_format",
        "starts_at",
        "ends_at",
        "reveal_at",
        "correct_answer",
        "explanation",
        "allow_multiple",
    ]
    serializer = StoryPatchSerializer(data=_request_data(request, fields))
    if not serializer.is_valid():
        return Response(
            {"error": "Check the form and try again.", "fields": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    data = serializer.validated_data
    if "title" in data and data["title"] is not None:
        title_limit = LEARNED_LIMIT if story.kind == CommunityStory.KIND_LEARNED else TITLE_LIMIT
        story.title = data["title"].strip()[:title_limit]
    if "body" in data and data["body"] is not None:
        story.body = data["body"].strip()
    if "campus_name" in data and data["campus_name"] is not None:
        story.campus_name = data["campus_name"].strip()
    if "status" in data and data["status"]:
        if data["status"] == CommunityStory.STATUS_REMOVED and not _is_staff(request.user):
            return Response({"error": "You cannot mark a story removed this way."}, status=status.HTTP_403_FORBIDDEN)
        story.status = data["status"]
    image = request.FILES.get("image")
    if image:
        image_error = _validate_image(image)
        if image_error:
            return Response({"error": image_error}, status=status.HTTP_400_BAD_REQUEST)
        story.image = image
    has_submissions = story.responses.filter(is_submission=True).exists()
    secret_keys = {"competition_format", "correct_answer", "allow_multiple"}
    if has_submissions and secret_keys.intersection(data.keys()) and not _is_staff(request.user):
        return Response(
            {"error": "The challenge format cannot change after students have submitted."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        _apply_competition_fields(story, data, creating=False)
    except serializers.ValidationError as exc:
        return Response({"error": _readable_validation(exc)}, status=status.HTTP_400_BAD_REQUEST)
    story.save()
    story = _base_queryset(request.user).get(pk=story.pk)
    return Response(serialize_story(story, request, detail=True))


def _visible_responses(story, user):
    qs = story.responses.select_related("user", "user__student_profile", "user__student_profile__university")
    if story.comments_hidden and story.creator_id != user.id and not _is_staff(user):
        rows = list(qs.order_by("created_at"))
        mine = {row.id for row in rows if row.user_id == user.id}
        by_id = {row.id: row for row in rows}
        visible = set(mine)
        for row in rows:
            if row.user_id != story.creator_id or not row.parent_id:
                continue
            parent_id = row.parent_id
            guard = 0
            while parent_id and guard < 8:
                if parent_id in mine:
                    visible.add(row.id)
                    break
                parent = by_id.get(parent_id)
                parent_id = parent.parent_id if parent else None
                guard += 1
        return [row for row in rows if row.id in visible]
    if _can_see_secrets(story, user):
        return qs.order_by("created_at")
    return qs.filter(user=user).order_by("created_at")


def serialize_response(resp, story, user):
    see_score = _can_see_secrets(story, user)
    payload = {
        "id": str(resp.id),
        "body": resp.body,
        "is_submission": resp.is_submission,
        "created_at": resp.created_at.isoformat(),
        "parent_id": str(resp.parent_id) if resp.parent_id else None,
        "author": _creator_payload(resp.user),
        "is_mine": resp.user_id == user.id,
    }
    if see_score and resp.score is not None:
        payload["score"] = resp.score
    return payload


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def story_responses(request, share_code):
    story = _get_visible_story(share_code, request.user)
    if story is None or story.status == CommunityStory.STATUS_REMOVED:
        return Response({"error": "This story is not available."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        try:
            page = max(int(request.GET.get("page", 1)), 1)
        except ValueError:
            page = 1
        try:
            page_size = int(request.GET.get("page_size", 20))
        except ValueError:
            page_size = 20
        page_size = min(max(page_size, 1), 50)
        responses = list(_visible_responses(story, request.user))
        paginator = Paginator(responses, page_size)
        current = paginator.get_page(page)
        return Response(
            {
                "count": paginator.count,
                "page": current.number,
                "page_size": page_size,
                "next": current.next_page_number() if current.has_next() else None,
                "results": [serialize_response(item, story, request.user) for item in current.object_list],
            }
        )

    limited = _rate_limit(request, "respond", 30, 600)
    if limited:
        return limited
    if story.status != CommunityStory.STATUS_ACTIVE:
        return Response({"error": "This story is closed."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = ResponseWriteSerializer(data=_request_data(request, ["body", "parent_id", "is_submission"]))
    if not serializer.is_valid():
        return Response(
            {"error": "Write a response before sending.", "fields": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    data = serializer.validated_data
    parent = None
    if data.get("parent_id"):
        parent = story.responses.filter(pk=data["parent_id"]).first()
        if parent is None:
            return Response({"error": "That reply target is not on this story."}, status=status.HTTP_400_BAD_REQUEST)

    is_submission = bool(data.get("is_submission"))
    if story.kind == CommunityStory.KIND_COMPETITION and parent is None and "is_submission" not in data:
        is_submission = True
    if parent is not None:
        is_submission = False
    if is_submission and story.kind != CommunityStory.KIND_COMPETITION:
        is_submission = False

    link = f"/stories/{story.share_code}"
    with transaction.atomic():
        locked = CommunityStory.objects.select_for_update().get(pk=story.pk)
        if is_submission:
            now = timezone.now()
            if locked.starts_at and now < locked.starts_at:
                return Response({"error": "This challenge has not started yet."}, status=status.HTTP_400_BAD_REQUEST)
            if competition_closed(locked, now):
                return Response({"error": "Submissions for this challenge are closed."}, status=status.HTTP_400_BAD_REQUEST)
            existing = CommunityResponse.objects.filter(
                story=locked, user=request.user, is_submission=True
            )
            if existing.exists() and not locked.allow_multiple:
                return Response(
                    {"error": "You have already submitted an answer."},
                    status=status.HTTP_409_CONFLICT,
                )
        score = None
        if is_submission and (locked.correct_answer or "").strip():
            expected = locked.correct_answer.strip().casefold()
            score = 1 if data["body"].strip().casefold() == expected else 0
        resp = CommunityResponse.objects.create(
            story=locked,
            user=request.user,
            parent=parent,
            body=data["body"].strip(),
            is_submission=is_submission,
            score=score,
        )
        locked.response_count = CommunityResponse.objects.filter(story=locked).count()
        locked.save(update_fields=["response_count", "updated_at"])

    if parent is not None and parent.user_id != request.user.id:
        _notify(
            parent.user,
            "New reply to your contribution",
            f'{request.user.display_name} replied on "{story.title}".',
            link,
        )
    elif story.creator_id != request.user.id:
        _notify(
            story.creator,
            "New response to your story",
            f'{request.user.display_name} responded to "{story.title}".',
            link,
        )

    if is_submission:
        count = (
            CommunityResponse.objects.filter(story=story, is_submission=True)
            .values("user_id")
            .distinct()
            .count()
        )
        if count in PARTICIPATION_MILESTONES and story.creator_id != request.user.id:
            title = f"{count} students joined your challenge"
            if not Notification.objects.filter(user=story.creator, link=link, title=title).exists():
                _notify(
                    story.creator,
                    title,
                    f'Students are taking part in "{story.title}".',
                    link,
                )

    resp = CommunityResponse.objects.select_related(
        "user", "user__student_profile", "user__student_profile__university"
    ).get(pk=resp.pk)
    return Response(serialize_response(resp, story, request.user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def story_appreciate(request, share_code):
    story = _get_visible_story(share_code, request.user)
    if story is None or story.status == CommunityStory.STATUS_REMOVED:
        return Response({"error": "This story is not available."}, status=status.HTTP_404_NOT_FOUND)
    limited = _rate_limit(request, "appreciate", 60, 60)
    if limited:
        return limited
    with transaction.atomic():
        existing = CommunityAppreciation.objects.filter(story=story, user=request.user).first()
        if existing:
            existing.delete()
            appreciated = False
        else:
            CommunityAppreciation.objects.create(story=story, user=request.user)
            appreciated = True
        story.appreciation_count = CommunityAppreciation.objects.filter(story=story).count()
        story.save(update_fields=["appreciation_count", "updated_at"])
    return Response({"appreciated": appreciated, "appreciation_count": story.appreciation_count})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def story_report(request, share_code):
    story = _get_visible_story(share_code, request.user)
    if story is None:
        return Response({"error": "This story is not available."}, status=status.HTTP_404_NOT_FOUND)
    limited = _rate_limit(request, "report", 10, 3600)
    if limited:
        return limited
    reason = (request.data.get("reason") or "").strip()
    if len(reason) < 3:
        return Response({"error": "Tell us briefly why you are reporting this."}, status=status.HTTP_400_BAD_REQUEST)
    if len(reason) > 500:
        return Response({"error": "Keep the report under 500 characters."}, status=status.HTTP_400_BAD_REQUEST)
    _, created = CommunityReport.objects.get_or_create(
        story=story,
        reporter=request.user,
        defaults={"reason": reason},
    )
    if created:
        notify_admin_users(
            "Community story reported",
            f'"{story.title}" was reported: {reason[:180]}',
            notification_type="warning",
            link=f"/stories/{story.share_code}",
        )
    return Response({"reported": True}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
