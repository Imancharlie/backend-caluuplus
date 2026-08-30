from django.urls import path

from . import views

urlpatterns = [
    path("university-calendar/", views.AcademicCalendarListView.as_view(), name="university-calendar"),
]
