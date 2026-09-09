"""
Serializers for advanced_features app
"""

from rest_framework import serializers
from .models import Notification, DeviceToken, NotificationPreference, MrCaluuMessage, MrCaluuSettings


class DeviceTokenSerializer(serializers.ModelSerializer):
    """Serializer for device token registration"""
    
    class Meta:
        model = DeviceToken
        fields = ['token', 'platform', 'device_info']
        extra_kwargs = {
            'token': {'required': True},
            'platform': {'required': True},
        }
    
    def create(self, validated_data):
        user = self.context['request'].user
        token = validated_data['token']
        
        # Check if token already exists for this user
        device_token = DeviceToken.objects.filter(
            user=user,
            token=token
        ).first()
        
        if device_token:
            # Update existing token
            device_token.platform = validated_data.get('platform', device_token.platform)
            device_token.device_info = validated_data.get('device_info', {})
            device_token.is_active = True
            device_token.save()
            return device_token
        
        # Create new token
        validated_data['user'] = user
        return super().create(validated_data)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences"""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'academic_deadlines',
            'opportunities',
            'articles',
            'promotions',
            'announcements',
            'token_warnings',
            'rewards',
            'welcome',
        ]
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'type',
            'title',
            'body',
            'data',
            'link',
            'created_at',
            'read_at',
            'sent_at',
            'sent_successfully',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'read_at',
            'sent_at',
            'sent_successfully',
        ]


class SendNotificationSerializer(serializers.Serializer):
    """Serializer for sending notifications (admin only)"""
    
    target_type = serializers.ChoiceField(
        choices=['all', 'user', 'role'],
        required=True
    )
    target_users = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True
    )
    target_role = serializers.ChoiceField(
        choices=['student', 'staff', 'admin'],
        required=False,
        allow_null=True
    )
    type = serializers.ChoiceField(
        choices=Notification.NOTIFICATION_TYPES,
        required=True
    )
    title = serializers.CharField(max_length=255, required=True)
    body = serializers.CharField(required=True)
    link = serializers.URLField(required=False, allow_null=True)
    data = serializers.DictField(required=False, default=dict)
    send_immediately = serializers.BooleanField(default=True)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)


class MrCaluuMessageSerializer(serializers.ModelSerializer):
    """Serializer for Mr. Caluu messages (admin CRUD)"""

    class Meta:
        model = MrCaluuMessage
        fields = [
            'id', 'text', 'image_url', 'links', 'display_order',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MrCaluuPublicSerializer(serializers.ModelSerializer):
    """Serializer for public Mr. Caluu messages"""

    class Meta:
        model = MrCaluuMessage
        fields = [
            'id', 'text', 'image_url', 'links', 'display_order', 'is_active'
        ]


class MrCaluuSettingsSerializer(serializers.ModelSerializer):
    """Serializer for Mr. Caluu settings"""

    class Meta:
        model = MrCaluuSettings
        fields = ['rotation_interval_seconds', 'updated_at']
        read_only_fields = ['updated_at']
