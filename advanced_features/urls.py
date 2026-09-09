"""
URL configuration for advanced_features app
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DeviceTokenViewSet,
    NotificationPreferenceViewSet,
    NotificationViewSet,
    AdminNotificationViewSet,
    MrCaluuMessageViewSet,
    MrCaluuPublicViewSet,
    MrCaluuSettingsView
)

router = DefaultRouter()
router.register(r'device-tokens', DeviceTokenViewSet, basename='device-token')
router.register(r'preferences', NotificationPreferenceViewSet, basename='notification-preference')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'admin', AdminNotificationViewSet, basename='admin-notification')
router.register(r'staff/mr-caluu-messages', MrCaluuMessageViewSet, basename='mr-caluu-staff')

urlpatterns = [
    path('', include(router.urls)),
    path('mr-caluu-messages/', MrCaluuPublicViewSet.as_view({'get': 'list'}), name='mr-caluu-public'),
    path('staff/mr-caluu-settings/', MrCaluuSettingsView.as_view(), name='mr-caluu-settings'),
]
