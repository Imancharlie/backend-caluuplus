from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AcademicCalendar
from .serializers import AcademicCalendarDataSerializer


class AcademicCalendarListView(APIView):
    """Return the academic calendar bundle (calendar + its events).

    Calendar data is public/read-only (administration happens in Django admin),
    so the endpoint is accessible without authentication.
    """

    permission_classes = [AllowAny]

    def _pick_calendar(self, request):
        queryset = AcademicCalendar.objects.select_related("university").all()

        calendar_id = request.query_params.get("calendar")
        if calendar_id:
            return queryset.filter(id=calendar_id).first()

        filters = {}
        university_id = request.query_params.get("university")
        if university_id:
            filters["university_id"] = university_id
        academic_year = request.query_params.get("academic_year")
        if academic_year:
            filters["academic_year"] = academic_year
        semester = request.query_params.get("semester")
        if semester:
            filters["semester"] = semester

        if not filters and hasattr(request, "user") and request.user and request.user.is_authenticated:
            student_profile = getattr(request.user, "student_profile", None)
            if student_profile is not None and getattr(student_profile, "university_id", None):
                filters = {"university_id": student_profile.university_id}

        candidates = queryset.filter(**filters) if filters else queryset

        active = candidates.filter(is_active=True).first()
        if active:
            return active
        return candidates.first()

    def get(self, request, *args, **kwargs):
        calendar = self._pick_calendar(request)
        if calendar is None:
            return Response(
                {"detail": "No academic calendar configured."},
                status=status.HTTP_404_NOT_FOUND,
            )

        events = list(calendar.events.filter(is_active=True))
        payload = AcademicCalendarDataSerializer({"calendar": calendar, "events": events}).data
        return Response(payload)
