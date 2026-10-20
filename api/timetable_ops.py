"""Timetable export, reminders, and class-representative announcements."""

import io
from datetime import datetime, timedelta

from django.http import HttpResponse
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    ClassRepresentative,
    Notification,
    Program,
    SessionChange,
    SessionReminderLog,
    SessionReminderPreference,
    Student,
    TimetableSlot,
)
from .permissions import user_is_admin

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CHANGE_STATUS = {
    "postponed": "postponed",
    "cancelled": "cancelled",
    "rescheduled": "postponed",
}


def _font(size):
    for path in (
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def slots_for_student(student, semester=None, academic_year=None):
    semester = student.semester if semester in (None, "") else semester
    academic_year = str(student.year) if not academic_year else str(academic_year)
    return TimetableSlot.objects.filter(
        student=student, semester=semester, academic_year=academic_year
    ).order_by("day_of_week", "time_slot")


def render_timetable_image(student, slots):
    width, height = 1400, 1000
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(28)
    body_font = _font(16)
    small_font = _font(14)
    draw.rectangle((0, 0, width, 72), fill="#041b31")
    draw.text((32, 20), "CALUU+  ·  Weekly timetable", fill="white", font=title_font)
    subtitle = (
        f"{student.user.display_name}    Year {student.year}    Semester {student.semester}"
    )
    draw.text((32, 92), subtitle, fill="#334155", font=body_font)

    days = WEEKDAYS[:5]
    times = []
    for slot in slots:
        if slot.time_slot not in times:
            times.append(slot.time_slot)
    times.sort()
    origin_x, origin_y = 32, 140
    col_w, row_h = 250, 64
    draw.rectangle((origin_x, origin_y, origin_x + 140, origin_y + 36), fill="#e0f2fe")
    draw.text((origin_x + 12, origin_y + 8), "Time", fill="#0f172a", font=small_font)
    for index, day in enumerate(days):
        x = origin_x + 140 + index * col_w
        draw.rectangle((x, origin_y, x + col_w - 8, origin_y + 36), fill="#e0f2fe")
        draw.text((x + 12, origin_y + 8), day.title(), fill="#0f172a", font=small_font)

    by_key = {(slot.day_of_week, slot.time_slot): slot for slot in slots}
    if not times:
        draw.text((origin_x, origin_y + 60), "No sessions scheduled.", fill="#64748b", font=body_font)
    for row, time_slot in enumerate(times[:12]):
        y = origin_y + 44 + row * row_h
        draw.text((origin_x + 8, y + 16), time_slot, fill="#334155", font=small_font)
        for index, day in enumerate(days):
            slot = by_key.get((day, time_slot))
            if slot is None:
                continue
            x = origin_x + 140 + index * col_w
            fill = "#fff7ed" if slot.status != "scheduled" else "#f8fafc"
            draw.rectangle((x, y, x + col_w - 8, y + row_h - 8), fill=fill, outline="#e2e8f0")
            name = slot.course_code or slot.course_name or "Class"
            venue = slot.venue or "Venue not set"
            state = "" if slot.status == "scheduled" else slot.status.upper()
            draw.text((x + 8, y + 6), str(name)[:28], fill="#0f172a", font=small_font)
            draw.text((x + 8, y + 26), f"{venue[:26]}  {state}".strip(), fill="#475569", font=small_font)
    return image


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def timetable_export(request):
    student = Student.objects.filter(user=request.user).select_related("user").first()
    if student is None:
        return Response({"error": "Student profile not found"}, status=status.HTTP_404_NOT_FOUND)
    image = render_timetable_image(
        student,
        list(slots_for_student(
            student,
            request.GET.get("semester"),
            request.GET.get("academic_year"),
        )),
    )
    buffer = io.BytesIO()
    export_format = (request.GET.get("file") or "png").lower()
    if export_format == "pdf":
        image.save(buffer, format="PDF")
        content_type = "application/pdf"
        filename = "caluu-timetable.pdf"
    else:
        image.save(buffer, format="PNG")
        content_type = "image/png"
        filename = "caluu-timetable.png"
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _active_reps(user, program_id=None):
    queryset = ClassRepresentative.objects.filter(user=user, is_active=True).select_related("program")
    if program_id:
        queryset = queryset.filter(program_id=program_id)
    return list(queryset)


def _programme_slots(user, program_id=None):
    reps = _active_reps(user, program_id)
    if reps:
        return reps, TimetableSlot.objects.filter(student__program__in=[rep.program for rep in reps])
    if user_is_admin(user):
        if not program_id:
            return [], TimetableSlot.objects.none()
        program = Program.objects.filter(id=program_id).first()
        if program is None:
            return [], TimetableSlot.objects.none()
        return [], TimetableSlot.objects.filter(student__program=program)
    return [], None


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def cr_sessions(request):
    program_id = request.GET.get("program")
    reps, slots = _programme_slots(request.user, program_id)
    if slots is None:
        return Response(
            {"error": "You are not a class representative for this programme"},
            status=status.HTTP_403_FORBIDDEN,
        )
    if user_is_admin(request.user) and not reps and not program_id:
        return Response({"error": "program is required"}, status=status.HTTP_400_BAD_REQUEST)
    if reps:
        scoped = TimetableSlot.objects.none()
        for rep in reps:
            cohort_slots = slots.filter(student__program=rep.program)
            if rep.cohort_year:
                cohort_slots = cohort_slots.filter(student__year=rep.cohort_year)
            scoped = scoped | cohort_slots
        slots = scoped
    grouped = {}
    for slot in slots.select_related("student"):
        key = (
            slot.course_code or "",
            slot.day_of_week,
            slot.time_slot,
            slot.semester,
            slot.academic_year,
            str(slot.student.program_id),
        )
        row = grouped.get(key)
        if row is None:
            grouped[key] = {
                "course_code": slot.course_code or "",
                "course_name": slot.course_name or "",
                "day_of_week": slot.day_of_week,
                "time_slot": slot.time_slot,
                "semester": slot.semester,
                "academic_year": slot.academic_year,
                "venue": slot.venue or "",
                "class_type": slot.class_type,
                "status": slot.status,
                "program": str(slot.student.program_id),
                "students": 1,
            }
        else:
            row["students"] += 1
    return Response({"sessions": list(grouped.values())})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def session_announcement(request):
    payload = request.data
    required = ["course_code", "day_of_week", "time_slot", "semester", "academic_year", "change_type", "message"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return Response({"error": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)
    change_type = payload["change_type"]
    if change_type not in CHANGE_STATUS:
        return Response({"error": "change_type must be postponed, cancelled, or rescheduled"}, status=status.HTTP_400_BAD_REQUEST)

    program_id = payload.get("program")
    reps = _active_reps(request.user, program_id)
    if reps:
        program = reps[0].program
        cohort_year = reps[0].cohort_year
    elif user_is_admin(request.user) and program_id:
        program = Program.objects.filter(id=program_id).first()
        cohort_year = None
        if program is None:
            return Response({"error": "Programme not found"}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(
            {"error": "You are not a class representative for this programme"},
            status=status.HTTP_403_FORBIDDEN,
        )

    course_code = str(payload["course_code"]).strip()
    day = str(payload["day_of_week"]).strip().lower()
    time_slot = str(payload["time_slot"]).strip()
    message = str(payload["message"]).strip()
    recent = SessionChange.objects.filter(
        program=program,
        course_code__iexact=course_code,
        day_of_week=day,
        time_slot=time_slot,
        change_type=change_type,
        created_by=request.user,
        created_at__gte=timezone.now() - timedelta(minutes=10),
    ).exists()
    if recent:
        return Response(
            {"error": "This announcement was already sent"},
            status=status.HTTP_409_CONFLICT,
        )

    matching = TimetableSlot.objects.filter(
        student__program=program,
        course_code__iexact=course_code,
        day_of_week=day,
        time_slot=time_slot,
        semester=payload["semester"],
        academic_year=str(payload["academic_year"]),
    ).select_related("student__user")
    if cohort_year:
        matching = matching.filter(student__year=cohort_year)
    affected = list(matching)
    if not affected:
        return Response(
            {"error": "No students in this programme have that session"},
            status=status.HTTP_404_NOT_FOUND,
        )

    new_status = CHANGE_STATUS[change_type]
    slot_ids = [slot.id for slot in affected]
    TimetableSlot.objects.filter(id__in=slot_ids).update(status=new_status, status_note=message)
    SessionReminderLog.objects.filter(slot_id__in=slot_ids, remind_on__gte=timezone.localdate()).delete()
    title = f"Class {change_type}: {course_code}"
    Notification.objects.bulk_create([
        Notification(
            user=slot.student.user,
            title=title,
            body=message,
            notification_type="warning",
        )
        for slot in affected
    ])
    change = SessionChange.objects.create(
        program=program,
        course_code=course_code,
        day_of_week=day,
        time_slot=time_slot,
        semester=payload["semester"],
        academic_year=str(payload["academic_year"]),
        change_type=change_type,
        message=message,
        affected_count=len(affected),
        created_by=request.user,
    )
    return Response(
        {"id": str(change.id), "affected_count": len(affected), "status": new_status},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def reminder_preference(request):
    preference, _ = SessionReminderPreference.objects.get_or_create(user=request.user)
    if request.method == "PUT":
        if "enabled" in request.data:
            preference.enabled = bool(request.data.get("enabled"))
        if "minutes_before" in request.data:
            try:
                minutes = int(request.data.get("minutes_before"))
            except (TypeError, ValueError):
                return Response({"error": "minutes_before must be a number"}, status=status.HTTP_400_BAD_REQUEST)
            preference.minutes_before = min(180, max(5, minutes))
        if "sms_consent" in request.data:
            preference.sms_consent = bool(request.data.get("sms_consent"))
        preference.save()
    return Response({
        "enabled": preference.enabled,
        "minutes_before": preference.minutes_before,
        "sms_consent": preference.sms_consent,
        "sms_available": False,
    })


def parse_start(time_slot):
    raw = (time_slot or "").split("-")[0].strip()
    if len(raw) != 4 or not raw.isdigit():
        return None
    return datetime.strptime(raw, "%H%M").time()


def send_due_reminders(now=None):
    """Create one in-app reminder per scheduled session inside the student's window."""
    current = timezone.localtime(now or timezone.now())
    weekday = WEEKDAYS[current.weekday()]
    sent = 0
    preferences = SessionReminderPreference.objects.filter(enabled=True).select_related("user")
    for preference in preferences:
        student = Student.objects.filter(user=preference.user).first()
        if student is None:
            continue
        slots = TimetableSlot.objects.filter(
            student=student,
            day_of_week=weekday,
            status="scheduled",
            semester=student.semester,
            academic_year=str(student.year),
        )
        for slot in slots:
            start = parse_start(slot.time_slot)
            if start is None:
                continue
            start_at = current.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
            minutes_until = (start_at - current).total_seconds() / 60
            if minutes_until < 0 or minutes_until > preference.minutes_before:
                continue
            _, created = SessionReminderLog.objects.get_or_create(
                user=preference.user,
                slot=slot,
                remind_on=current.date(),
                minutes_before=preference.minutes_before,
            )
            if not created:
                continue
            venue = slot.venue or "venue to be confirmed"
            Notification.objects.create(
                user=preference.user,
                title=f"Upcoming: {slot.course_code or slot.course_name or 'Class'}",
                body=f"{slot.time_slot} at {venue}",
                notification_type="info",
            )
            sent += 1
    return sent
