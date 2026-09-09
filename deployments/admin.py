from django.contrib import admin

from .models import Deployment


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    list_display = [
        "status", "branch", "short_before", "short_after", "trigger",
        "duration_seconds", "started_at", "finished_at",
    ]
    list_filter = ["status", "trigger", "branch"]
    search_fields = ["commit_before", "commit_after", "error_summary", "log"]
    readonly_fields = [f.name for f in Deployment._meta.get_fields()]
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        # Deployments are created by the pipeline, never manually.
        return False

    def has_change_permission(self, request, obj=None):
        # Deployment history is immutable/auditable.
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def short_before(self, obj):
        return (obj.commit_before or "")[:12] or "-"

    def short_after(self, obj):
        return (obj.commit_after or "")[:12] or "-"

    short_before.short_description = "before"
    short_after.short_description = "after"