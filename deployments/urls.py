from django.urls import path

from . import views

urlpatterns = [
    path("", views.DeploymentListView.as_view(), name="deployment-list"),
    path("<uuid:pk>/", views.DeploymentDetailView.as_view(), name="deployment-detail"),
]