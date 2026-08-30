import uuid

from django.db import models


class AcademicCalendar(models.Model):
    """A university's academic calendar for a given year/semester.

    This is the source of truth that drives the mobile Academic Timeline.
    A university can have multiple calendars (different academic years and/or
    semesters); exactly one is usually marked ``is_active`` and returned by the
    public ``/university-calendar/`` endpoint unless a specific calendar is
    requested.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    university = models.ForeignKey(
        "api.University",
        on_delete=models.CASCADE,
        related_name="academic_calendars",
    )
    academic_year = models.CharField(
        max_length=20,
        help_text="e.g. 2024/2025",
    )
    semester = models.CharField(
        max_length=50,
        default="Semester 1",
        help_text="e.g. Semester 1, Semester 2",
    )
    start_date = models.DateField(help_text="Semester start date. Used to derive semester weeks.")
    end_date = models.DateField(help_text="Semester end date.")
    is_active = models.BooleanField(
        default=True,
        help_text="Mark as the current calendar to be returned when no specific calendar is requested.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "start_date"]
        verbose_name = "Academic Calendar"
        verbose_name_plural = "Academic Calendars"
        constraints = [
            models.UniqueConstraint(
                fields=["university", "academic_year", "semester", "is_active"],
                name="uniq_active_calendar_per_university",
                condition=models.Q(is_active=True),
            )
        ]

    def __str__(self):
        return f"{self.university.name} - {self.academic_year} ({self.semester})"


class AcademicEvent(models.Model):
    """A single calendar fact (point event or date range) in a calendar."""

    EVENT_TYPES = [
        ("registration", "Registration"),
        ("orientation", "Orientation"),
        ("lectures", "Lectures Begin"),
        ("mid_semester", "Mid-Semester"),
        ("examination", "Examinations"),
        ("break", "Break"),
        ("holiday", "Holiday"),
        ("results", "Results"),
        ("graduation", "Graduation"),
        ("academic", "Academic"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(
        AcademicCalendar,
        on_delete=models.CASCADE,
        related_name="events",
    )
    title = models.CharField(max_length=200)
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        default="academic",
    )
    start_date = models.DateField(help_text="Start date (YYYY-MM-DD). A single-day event only needs this.")
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date (YYYY-MM-DD). Leave empty for a single-day/point event.",
    )
    description = models.TextField(blank=True, null=True)
    order = models.IntegerField(
        default=0,
        help_text="Optional sort order within the timeline (lower first).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive events are hidden from the timeline.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "start_date"]
        verbose_name = "Academic Event"
        verbose_name_plural = "Academic Events"

    def __str__(self):
        return f"{self.title} ({self.start_date})"
