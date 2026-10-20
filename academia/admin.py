from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import AcademicCalendar, AcademicEvent, GlobalSemesterCalendar


class AcademicEventInline(admin.TabularInline):
    model = AcademicEvent
    extra = 0
    fields = ("title", "event_type", "start_date", "end_date", "order", "is_active")
    ordering = ("order", "start_date")


@admin.register(AcademicCalendar)
class AcademicCalendarAdmin(admin.ModelAdmin):
    list_display = ("university", "academic_year", "semester", "start_date", "end_date", "is_active")
    list_filter = ("university", "semester", "is_active", "start_date")
    search_fields = ("university__name", "academic_year", "semester")
    list_editable = ("is_active",)
    inlines = (AcademicEventInline,)
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("university", "academic_year", "semester")}),
        ("Dates", {"fields": ("start_date", "end_date")}),
        ("Status", {"fields": ("is_active",)}),
        ("Meta", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(AcademicEvent)
class AcademicEventAdmin(admin.ModelAdmin):
    list_display = ("title", "calendar", "event_type", "start_date", "end_date", "order", "is_active")
    list_filter = ("event_type", "is_active", "calendar__university", "start_date")
    search_fields = ("title", "description", "calendar__university__name")
    list_editable = ("is_active", "order")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("calendar", "title", "event_type")}),
        ("Dates", {"fields": ("start_date", "end_date")}),
        ("Details", {"fields": ("description", "order", "is_active")}),
        ("Meta", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


class GlobalSemesterCalendarForm(forms.ModelForm):
    class Meta:
        model = GlobalSemesterCalendar
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        for start_name, end_name, label in (
            ("semester_1_start", "semester_1_end", "Semester 1"),
            ("semester_2_start", "semester_2_end", "Semester 2"),
        ):
            start = cleaned.get(start_name)
            end = cleaned.get(end_name)
            if (start is None) != (end is None):
                raise ValidationError(f"{label} needs both a start date and an end date.")
            if start and end and end < start:
                raise ValidationError(f"{label} end date is before the start date.")
        return cleaned


@admin.register(GlobalSemesterCalendar)
class GlobalSemesterCalendarAdmin(admin.ModelAdmin):
    form = GlobalSemesterCalendarForm
    fieldsets = (
        ("Semester 1 — used for every university", {"fields": ("semester_1_start", "semester_1_end")}),
        ("Semester 2 — used for every university", {"fields": ("semester_2_start", "semester_2_end")}),
    )

    def has_add_permission(self, request):
        return not GlobalSemesterCalendar.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
