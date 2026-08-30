from rest_framework import serializers

from .models import AcademicCalendar, AcademicEvent


class AcademicEventSerializer(serializers.ModelSerializer):
    """Output shape matches the mobile Academic Timeline's AcademicEvent type."""

    type = serializers.CharField(source="event_type", read_only=True)

    class Meta:
        model = AcademicEvent
        fields = ("id", "title", "type", "start_date", "end_date", "description")

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
