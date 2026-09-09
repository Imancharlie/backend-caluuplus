from django.db import models
from django.conf import settings
import uuid


class MrCaluuMessage(models.Model):
    """Mr. Caluu motivational message"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField(help_text="Message text with markdown-style bold (**bold**)")
    image = models.ImageField(
        upload_to='mr_caluu/',
        blank=True,
        null=True,
        help_text="Uploaded image shown in the carousel"
    )
    image_url = models.URLField(blank=True, null=True, help_text="External image URL as a fallback")
    links = models.JSONField(default=list, blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"MrCaluu: {self.text[:50]}..."

    @property
    def text_preview(self):
        return self.text[:100] + '...' if len(self.text) > 100 else self.text

    @property
    def image_display(self):
        """Return the effective image URL for display (uploaded image wins, falls back to external URL)."""
        if self.image:
            return self.image.url
        if self.image_url:
            return self.image_url
        return None


class MrCaluuSettings(models.Model):
    """Singleton settings for Mr. Caluu"""
    rotation_interval_seconds = models.IntegerField(default=1800, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mr. Caluu Settings"
        verbose_name_plural = "Mr. Caluu Settings"

    def __str__(self):
        return f"Rotation interval: {self.rotation_interval_seconds}s"

    def save(self, *args, **kwargs):
        self.pk = 1  # Ensure singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Notification(models.Model):
    """Notification model for storing push notifications"""
    
    NOTIFICATION_TYPES = [
        ('academic_deadline', 'Academic Deadline'),
        ('opportunity', 'Opportunity'),
        ('article', 'Article'),
        ('promotion', 'Promotion'),
        ('announcement', 'Announcement'),
        ('token_warning', 'Token Warning'),
        ('reward', 'Reward'),
        ('welcome', 'Welcome'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='advanced_notifications'
    )
    type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    link = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_successfully = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['type']),
            models.Index(fields=['read_at']),
        ]
    
    def __str__(self):
        return f"{self.type} - {self.title}"
    
    def mark_as_read(self):
        from django.utils import timezone
        self.read_at = timezone.now()
        self.save(update_fields=['read_at'])


class DeviceToken(models.Model):
    """FCM device tokens for push notifications"""
    
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens'
    )
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    device_info = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-last_used']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['token']),
        ]
    
    def __str__(self):
        return f"{self.platform} - {self.user.email}"


class NotificationPreference(models.Model):
    """User notification preferences"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    academic_deadlines = models.BooleanField(default=True)
    opportunities = models.BooleanField(default=True)
    articles = models.BooleanField(default=True)
    promotions = models.BooleanField(default=True)
    announcements = models.BooleanField(default=True)
    token_warnings = models.BooleanField(default=True)
    rewards = models.BooleanField(default=True)
    welcome = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"
    
    def __str__(self):
        return f"Preferences for {self.user.email}"
