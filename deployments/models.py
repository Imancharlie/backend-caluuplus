"""
Auto-deploy audit subsystem.

Records every automated deployment of the backend so releases are
traceable: which commit was deployed, who/what triggered it, how long it
took, and whether it succeeded or was rolled back.

The `manage.py deploy` pipeline writes these records; the admin dashboard
and the read-only REST API (`GET /api/deployments/`) expose them.
"""

import uuid

from django.db import models


class DeploymentStatus(models.TextChoices):
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    ROLLED_BACK = "rolled_back", "Rolled Back"
    FAILED = "failed", "Failed"


class DeploymentTrigger(models.TextChoices):
    TIMER = "timer", "Timer"
    MANUAL = "manual", "Manual"


class Deployment(models.Model):
    """One automated deploy attempt (or rollback)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.CharField(max_length=64, default="main")
    commit_before = models.CharField(max_length=40, blank=True, default="")
    commit_after = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=DeploymentStatus.choices,
        default=DeploymentStatus.RUNNING,
        db_index=True,
    )
    trigger = models.CharField(
        max_length=16, choices=DeploymentTrigger.choices, default=DeploymentTrigger.TIMER
    )
    log = models.TextField(blank=True, default="")
    error_summary = models.TextField(blank=True, default="")
    db_backup_path = models.CharField(
        max_length=512, blank=True, default="",
        help_text="SQLite snapshot taken before migrations, used for rollback.",
    )
    duration_seconds = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Deployment"
        verbose_name_plural = "Deployments"
        indexes = [
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self):
        after = (self.commit_after or self.commit_before or "?")[:7]
        return f"{self.status} {after} @ {self.started_at:%Y-%m-%d %H:%M}"