"""URL routing for the Caluu Map API (mounted at ``api/map/``)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BuildingViewSet,
    CampusContributorViewSet,
    CampusViewSet,
    MapSearchView,
    NearbyView,
    PathEdgeViewSet,
    PathNodeViewSet,
    PhotoViewSet,
    PlaceViewSet,
    ReportCorrectionViewSet,
    SyncDataView,
)

router = DefaultRouter()
router.register("campuses", CampusViewSet, basename="map-campus")
router.register("buildings", BuildingViewSet, basename="map-building")
router.register("places", PlaceViewSet, basename="map-place")
router.register("photos", PhotoViewSet, basename="map-photo")
router.register("path-nodes", PathNodeViewSet, basename="map-pathnode")
router.register("path-edges", PathEdgeViewSet, basename="map-pathedge")
router.register(
    "campus-contributors", CampusContributorViewSet, basename="map-contributor"
)
router.register(
    "correction-reports", ReportCorrectionViewSet, basename="map-report"
)

urlpatterns = [
    path("", include(router.urls)),
    path("sync/", SyncDataView.as_view(), name="map-sync"),
    path("search/", MapSearchView.as_view(), name="map-search"),
    path("nearby/", NearbyView.as_view(), name="map-nearby"),
]