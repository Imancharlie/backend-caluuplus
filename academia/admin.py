from django.contrib import admin

from .models import AcademicCalendar, AcademicEvent


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
