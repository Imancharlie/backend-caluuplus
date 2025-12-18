from django.urls import path

from .views import BackupDashboardView

app_name = "backups"

urlpatterns = [
    path("", BackupDashboardView.as_view(), name="dashboard"),
]










