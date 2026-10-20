import uuid

from django.db import models
from django.conf import settings
from api.models import University  # assuming this exists

class Resource(models.Model):
    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, blank=True, related_name='resources')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='resources/files/')
    file_type = models.CharField(max_length=50, blank=True)  # optional, derive from file
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Opportunity(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('seminar', 'Seminar'),
        ('competition', 'Competition'),
        ('job', 'Job'),
        ('meeting', 'Meeting'),
        ('scholarship', 'Scholarship'),
        ('internship', 'Internship'),
        ('online_course', 'Online Course'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=255)
    cover_media = models.FileField(upload_to='opportunities/media/', blank=True, null=True)
    media_type = models.CharField(max_length=10, choices=[('image', 'Image'), ('video', 'Video')], blank=True)
    content = models.TextField()  # full explanation
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    application_url = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active = models.BooleanField(default=False)  # Only true when approved

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class OpportunityReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='opportunity_reports'
    )
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['opportunity', 'reporter'], name='unique_opportunity_report'),
        ]

    def __str__(self):
        return f"Report on {self.opportunity_id}"
