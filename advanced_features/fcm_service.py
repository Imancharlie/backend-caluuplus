"""
FCM Service for Firebase Cloud Messaging
Handles sending push notifications to mobile devices
"""

import logging
from typing import List, Optional, Dict, Any
from django.utils import timezone
from .models import DeviceToken, Notification

logger = logging.getLogger(__name__)

# Firebase Admin SDK import - will be None if not installed
firebase_messaging = None
try:
    from firebase_admin import messaging
    firebase_messaging = messaging
except ImportError:
    logger.warning("firebase-admin not installed. Push notifications will not work.")


class FCMService:
    """Service for sending Firebase Cloud Messages"""
    
    @staticmethod
    def is_available() -> bool:
        """Check if FCM service is available"""
        return firebase_messaging is not None
    
    @staticmethod
    def send_to_device(
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_id: Optional[str] = None
    ) -> bool:
        """
        Send push notification to a single device
        
        Args:
            token: FCM device token
            title: Notification title
            body: Notification body
            data: Additional data payload
            notification_id: Notification ID for tracking
            
        Returns:
            bool: True if sent successfully
        """
        if not FCMService.is_available():
            logger.error("FCM service not available")
            return False
        
        try:
            message = firebase_messaging.Message(
                notification=firebase_messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
                android=firebase_messaging.AndroidConfig(
                    priority='high',
                    notification=firebase_messaging.AndroidNotification(
                        channel_id='caluu_notifications',
                        sound='default',
                    ),
                ),
                apns=firebase_messaging.APNSConfig(
                    payload=firebase_messaging.APNSPayload(
                        aps=firebase_messaging.Aps(
                            sound='default',
                            badge=1,
                        ),
                    ),
                ),
            )
            
            response = firebase_messaging.send(message)
            logger.info(f"FCM message sent successfully: {response}")
            
            # Update notification if ID provided
            if notification_id:
                try:
                    notification = Notification.objects.get(id=notification_id)
                    notification.sent_at = timezone.now()
                    notification.sent_successfully = True
                    notification.save(update_fields=['sent_at', 'sent_successfully'])
                except Notification.DoesNotExist:
                    pass
            
            return True
            
        except firebase_messaging.InvalidAPNSCredentials:
            logger.error("Invalid APNS credentials")
            return False
        except firebase_messaging.InvalidArgumentError as e:
            logger.error(f"Invalid FCM argument: {e}")
            return False
        except firebase_messaging.UnregisteredError:
            logger.warning(f"Device token unregistered: {token}")
            # Deactivate the token
            DeviceToken.objects.filter(token=token).update(is_active=False)
            return False
        except Exception as e:
            logger.error(f"Error sending FCM message: {e}")
            return False
    
    @staticmethod
    def send_to_multiple_devices(
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple devices
        
        Args:
            tokens: List of FCM device tokens
            title: Notification title
            body: Notification body
            data: Additional data payload
            notification_id: Notification ID for tracking
            
        Returns:
            Dict with success count and failure count
        """
        if not FCMService.is_available():
            logger.error("FCM service not available")
            return {'success': 0, 'failure': len(tokens)}
        
        if not tokens:
            return {'success': 0, 'failure': 0}
        
        try:
            message = firebase_messaging.MulticastMessage(
                notification=firebase_messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                tokens=tokens,
                android=firebase_messaging.AndroidConfig(
                    priority='high',
                    notification=firebase_messaging.AndroidNotification(
                        channel_id='caluu_notifications',
                        sound='default',
                    ),
                ),
                apns=firebase_messaging.APNSConfig(
                    payload=firebase_messaging.APNSPayload(
                        aps=firebase_messaging.Aps(
                            sound='default',
                            badge=1,
                        ),
                    ),
                ),
            )
            
            response = firebase_messaging.send_multicast(message)
            
            logger.info(
                f"FCM multicast sent: {response.success_count} success, "
                f"{response.failure_count} failure"
            )
            
            # Update notification if ID provided
            if notification_id and response.success_count > 0:
                try:
                    notification = Notification.objects.get(id=notification_id)
                    notification.sent_at = timezone.now()
                    notification.sent_successfully = response.success_count > 0
                    notification.save(update_fields=['sent_at', 'sent_successfully'])
                except Notification.DoesNotExist:
                    pass
            
            # Handle failed tokens
            if response.failure_count > 0:
                for idx, error in enumerate(response.responses):
                    if not error.success:
                        if error.exception and isinstance(
                            error.exception, 
                            (firebase_messaging.UnregisteredError, 
                             firebase_messaging.InvalidArgumentError)
                        ):
                            token = tokens[idx]
                            DeviceToken.objects.filter(token=token).update(is_active=False)
            
            return {
                'success': response.success_count,
                'failure': response.failure_count,
            }
            
        except Exception as e:
            logger.error(f"Error sending FCM multicast: {e}")
            return {'success': 0, 'failure': len(tokens)}
    
    @staticmethod
    def send_to_user(
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_type: Optional[str] = None,
        link: Optional[str] = None,
        notification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to all active devices of a user
        
        Args:
            user_id: User ID
            title: Notification title
            body: Notification body
            data: Additional data payload
            notification_type: Type of notification
            link: Deep link URL
            notification_id: Notification ID for tracking
            
        Returns:
            Dict with success count and failure count
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"User not found: {user_id}")
            return {'success': 0, 'failure': 0}
        
        # Get active device tokens for user
        device_tokens = DeviceToken.objects.filter(
            user=user,
            is_active=True
        ).values_list('token', flat=True)
        
        if not device_tokens:
            logger.info(f"No active device tokens for user: {user_id}")
            return {'success': 0, 'failure': 0}
        
        # Add notification type and link to data
        payload_data = data or {}
        if notification_type:
            payload_data['type'] = notification_type
        if link:
            payload_data['link'] = link
        
        return FCMService.send_to_multiple_devices(
            tokens=list(device_tokens),
            title=title,
            body=body,
            data=payload_data,
            notification_id=notification_id,
        )
    
    @staticmethod
    def send_to_topic(
        topic: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send push notification to a topic
        
        Args:
            topic: FCM topic name
            title: Notification title
            body: Notification body
            data: Additional data payload
            
        Returns:
            bool: True if sent successfully
        """
        if not FCMService.is_available():
            logger.error("FCM service not available")
            return False
        
        try:
            message = firebase_messaging.Message(
                notification=firebase_messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                topic=topic,
                android=firebase_messaging.AndroidConfig(
                    priority='high',
                    notification=firebase_messaging.AndroidNotification(
                        channel_id='caluu_notifications',
                        sound='default',
                    ),
                ),
                apns=firebase_messaging.APNSConfig(
                    payload=firebase_messaging.APNSPayload(
                        aps=firebase_messaging.Aps(
                            sound='default',
                            badge=1,
                        ),
                    ),
                ),
            )
            
            response = firebase_messaging.send(message)
            logger.info(f"FCM topic message sent successfully: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending FCM topic message: {e}")
            return False
