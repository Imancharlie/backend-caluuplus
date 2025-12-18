from django.contrib import admin

from .models import BackupRecord, BackupSettings


@admin.register(BackupSettings)
class BackupSettingsAdmin(admin.ModelAdmin):
    list_display = ["automatic_enabled", "scheduled_time", "retention_days", "notify_email"]
    readonly_fields = ["created_at", "updated_at", "last_automatic_run"]


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ["created_at", "backup_type", "status", "file_size", "created_by"]
    list_filter = ["backup_type", "status", "created_at"]
    search_fields = ["file_path", "notes"]
    readonly_fields = [
        "created_at",
        "created_by",
        "duration_seconds",
        "file_path",
        "file_size",
        "restored_at",
        "restored_by",
    ]










