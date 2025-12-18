from __future__ import annotations

from datetime import time
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BackupSettings(models.Model):
    """Configuration for automated backups."""

    automatic_enabled = models.BooleanField(default=False)
    scheduled_time = models.TimeField(default=time(hour=1, minute=0))
    retention_days = models.PositiveIntegerField(default=14)
    notify_email = models.EmailField(blank=True)
    include_media = models.BooleanField(
        default=False,
        help_text="Include media files in archive backups (may increase runtime).",
    )
    last_automatic_run = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Backup Setting"
        verbose_name_plural = "Backup Settings"

    def clean(self) -> None:
        if self.retention_days == 0:
            raise ValidationError("Retention days must be greater than zero.")

    def save(self, *args, **kwargs) -> None:
        """Ensure a singleton instance by forcing the primary key."""

        self.full_clean()
        if not self.pk:
            existing = BackupSettings.objects.first()
            if existing:
                self.pk = existing.pk
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        status = "enabled" if self.automatic_enabled else "disabled"
        return f"Backup settings ({status})"

    @classmethod
    def load(cls) -> "BackupSettings":
        instance = cls.objects.first()
        if instance:
            return instance
        instance = cls.objects.create()
        return instance

    @property
    def effective_notify_email(self) -> Optional[str]:
        if self.notify_email:
            return self.notify_email
        return getattr(settings, "BACKUP_NOTIFY_EMAIL", None)


class BackupRecord(models.Model):
    """History entry for each backup attempt."""

    class BackupType(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATIC = "automatic", "Automatic"

    class BackupStatus(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        RESTORED = "restored", "Restored"

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    backup_type = models.CharField(
        max_length=20, choices=BackupType.choices, default=BackupType.MANUAL
    )
    status = models.CharField(
        max_length=20, choices=BackupStatus.choices, default=BackupStatus.SUCCESS
    )
    file_path = models.CharField(max_length=512)
    file_size = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restored_backups",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Backup Record"
        verbose_name_plural = "Backup Records"

    def mark_restored(self, user=None) -> None:
        self.status = self.BackupStatus.RESTORED
        self.restored_by = user
        from django.utils import timezone

        self.restored_at = timezone.now()
        self.save(update_fields=["status", "restored_by", "restored_at"])

    @property
    def size_mb(self) -> Optional[float]:
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return None

    def __str__(self) -> str:
        return f"Backup {self.created_at:%Y-%m-%d %H:%M:%S} ({self.backup_type})"
