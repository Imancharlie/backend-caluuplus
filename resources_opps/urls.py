from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ResourceViewSet, OpportunityViewSet

router = DefaultRouter()
router.register(r'resources', ResourceViewSet)
router.register(r'opportunities', OpportunityViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
