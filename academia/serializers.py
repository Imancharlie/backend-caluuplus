from rest_framework import serializers
from django.utils import timezone
from datetime import datetime, time

from .models import AcademicCalendar, AcademicEvent


class AcademicEventSerializer(serializers.ModelSerializer):
    """Output shape matches the mobile Academic Timeline's AcademicEvent type."""

    type = serializers.CharField(source="event_type", read_only=True)
    # Server-computed countdown (whole calendar days until the event's start,
    # in Africa/Dar_es_Salaam). 0 = today, negative = already started/past.
    # Frontends should prefer this over re-deriving the countdown locally,
    # which is prone to UTC-midnight parsing skew (`new Date("YYYY-MM-DD")`
    # is parsed as UTC, inflating the count by one in UTC+3).
    days_until = serializers.SerializerMethodField(read_only=True)
    # Timezone-qualified ISO instants (local midnight, UTC+3). Parsing these
    # yields the correct local start-of-day in any timezone-aware client.
    start_date_iso = serializers.SerializerMethodField(read_only=True)
    end_date_iso = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AcademicEvent
        fields = (
            "id", "title", "type", "start_date", "end_date", "description",
            "days_until", "start_date_iso", "end_date_iso",
        )

    @staticmethod
    def _localized_midnight(date_obj):
        if not date_obj:
            return None
        return timezone.make_aware(datetime.combine(date_obj, time.min)).isoformat()

    def get_days_until(self, obj):
        if not obj.start_date:
            return None
        return (obj.start_date - timezone.localdate()).days

    def get_start_date_iso(self, obj):
        return self._localized_midnight(obj.start_date)

    def get_end_date_iso(self, obj):
        return self._localized_midnight(obj.end_date)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # end_date is optional in the mobile type (null for single-day events).
        data["end_date"] = data.get("end_date")
        return data


class AcademicCalendarSerializer(serializers.ModelSerializer):
    """Output shape matches the mobile Academic Timeline's AcademicCalendar type."""

    university = serializers.CharField(source="university_id", read_only=True)

    class Meta:
        model = AcademicCalendar
        fields = ("id", "university", "academic_year", "semester", "start_date", "end_date")


class AcademicCalendarDataSerializer(serializers.Serializer):
    """Bundle returned by /university-calendar/ — a calendar plus its events."""

    calendar = AcademicCalendarSerializer()
    events = serializers.ListField(child=AcademicEventSerializer())
