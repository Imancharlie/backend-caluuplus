from django.db import models
from django.conf import settings
import uuid


class ImportJob(models.Model):
    """Track import operations and their status"""
    IMPORT_TYPES = [
        ('university_programs', 'University, College, Programs'),
        ('courses', 'Courses'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partially_failed', 'Partially Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_type = models.CharField(max_length=50, choices=IMPORT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='import_jobs')
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.import_type} - {self.filename} ({self.status})"


class ImportError(models.Model):
    """Track errors that occurred during import operations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name='errors')
    row_number = models.IntegerField()
    error_type = models.CharField(max_length=50, choices=[
        ('missing_field', 'Missing Required Field'),
        ('invalid_data', 'Invalid Data Format'),
        ('duplicate_entry', 'Duplicate Entry'),
        ('dependency_missing', 'Missing Dependency'),
        ('validation_error', 'Validation Error'),
        ('system_error', 'System Error'),
    ])
    field_name = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField()
    original_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Row {self.row_number}: {self.error_type} - {self.error_message}"


class RetryJob(models.Model):
    """Track retry operations for failed imports"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_import_job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name='retry_jobs')
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    total_errors = models.IntegerField(default=0)
    resolved_errors = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Retry for {self.original_import_job} - {self.status}"
