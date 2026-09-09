"""
API Views for advanced_features app
"""

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Notification, DeviceToken, NotificationPreference, MrCaluuMessage, MrCaluuSettings
from .serializers import (
    DeviceTokenSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    SendNotificationSerializer,
    MrCaluuMessageSerializer,
    MrCaluuPublicSerializer,
    MrCaluuSettingsSerializer
)
from .fcm_service import FCMService

User = get_user_model()


class DeviceTokenViewSet(viewsets.ModelViewSet):
    """ViewSet for device token management"""
    serializer_class = DeviceTokenSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['delete'])
    def unregister(self, request):
        """Unregister current device token"""
        token = request.data.get('token')
        if not token:
            return Response(
                {'error': 'Token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        DeviceToken.objects.filter(
            user=request.user,
            token=token
        ).update(is_active=False)
        
        return Response({'message': 'Device unregistered successfully'})


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for notification preferences"""
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)
    
    def get_object(self):
        # Get or create preferences for the user
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)
        
        # Filter by read status
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            if is_read.lower() == 'true':
                queryset = queryset.filter(read_at__isnull=False)
            else:
                queryset = queryset.filter(read_at__isnull=True)
        
        # Filter by type
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(type=notification_type)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'message': 'Notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read"""
        Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({'message': 'All notifications marked as read'})
    
    @action(detail=True, methods=['delete'])
    def delete(self, request, pk=None):
        """Delete a notification"""
        notification = self.get_object()
        notification.delete()
        return Response({'message': 'Notification deleted'})


class AdminNotificationViewSet(viewsets.ViewSet):
    """ViewSet for admin notification management"""
    permission_classes = [IsAdminUser]
    
    @action(detail=False, methods=['post'])
    def send(self, request):
        """Send notification to users"""
        serializer = SendNotificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        target_type = data['target_type']
        notification_type = data['type']
        title = data['title']
        body = data['body']
        link = data.get('link')
        extra_data = data.get('data', {})
        
        # Get target users
        target_users = []
        if target_type == 'all':
            target_users = User.objects.all()
        elif target_type == 'user':
            target_users = User.objects.filter(id__in=data['target_users'])
        elif target_type == 'role':
            if data['target_role'] == 'student':
                target_users = User.objects.filter(is_student=True)
            elif data['target_role'] == 'staff':
                target_users = User.objects.filter(is_staff=True, is_superuser=False)
            elif data['target_role'] == 'admin':
                target_users = User.objects.filter(is_superuser=True)
        
        if not target_users:
            return Response(
                {'error': 'No target users found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create and send notifications
        sent_count = 0
        failed_count = 0
        
        for user in target_users:
            # Check user preferences
            try:
                preferences = user.notification_preferences
                if not getattr(preferences, notification_type, True):
                    continue
            except NotificationPreference.DoesNotExist:
                # User has no preferences, send by default
                pass
            
            # Create notification record
            notification = Notification.objects.create(
                recipient=user,
                type=notification_type,
                title=title,
                body=body,
                data=extra_data,
                link=link,
            )
            
            # Send push notification
            result = FCMService.send_to_user(
                user_id=str(user.id),
                title=title,
                body=body,
                data=extra_data,
                notification_type=notification_type,
                link=link,
                notification_id=str(notification.id),
            )
            
            sent_count += result.get('success', 0)
            failed_count += result.get('failure', 0)
        
        return Response({
            'message': 'Notifications sent',
            'sent_count': sent_count,
            'failed_count': failed_count,
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get notification statistics"""
        total_notifications = Notification.objects.count()
        unread_notifications = Notification.objects.filter(read_at__isnull=True).count()
        active_devices = DeviceToken.objects.filter(is_active=True).count()
        
        return Response({
            'total_notifications': total_notifications,
            'unread_notifications': unread_notifications,
            'active_devices': active_devices,
        })


class MrCaluuMessageViewSet(viewsets.ModelViewSet):
    """Admin ViewSet for Mr. Caluu messages management"""
    queryset = MrCaluuMessage.objects.all()
    serializer_class = MrCaluuMessageSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['is_active']
    search_fields = ['text']


class MrCaluuPublicViewSet(viewsets.ReadOnlyModelViewSet):
    """Public ViewSet for active Mr. Caluu messages"""
    queryset = MrCaluuMessage.objects.filter(is_active=True)
    serializer_class = MrCaluuPublicSerializer
    permission_classes = [AllowAny]

    def _resolve_username(self, request):
        """Resolve the requesting user's first name for the {username} token.

        Uses the authenticated JWT user's display name (first word = first name).
        Falls back to 'friend' when unauthenticated or no name is available.
        """
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            display_name = (getattr(user, 'display_name', '') or '').strip()
            if display_name:
                # First word of the display name is treated as the first name
                first_name = display_name.split()[0]
                return first_name
        return 'friend'

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        username = self._resolve_username(request)

        messages = serializer.data
        for message in messages:
            if message.get('text') and '{username}' in message['text']:
                message['text'] = message['text'].replace('{username}', username)

        settings_obj = MrCaluuSettings.load()
        return Response({
            'messages': messages,
            'rotation_interval_seconds': settings_obj.rotation_interval_seconds or 1800,
        })


class MrCaluuSettingsView(generics.RetrieveUpdateAPIView):
    """Admin view to get/update Mr. Caluu settings"""
    queryset = MrCaluuSettings.objects.all()
    serializer_class = MrCaluuSettingsSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        return MrCaluuSettings.load()
