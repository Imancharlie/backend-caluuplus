from rest_framework import serializers

from .models import Deployment


class DeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deployment
        fields = [
            "id", "branch", "commit_before", "commit_after", "status",
            "trigger", "error_summary", "duration_seconds", "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class DeploymentDetailSerializer(DeploymentSerializer):
    """List fields plus the full deployment log (for the detail view)."""

    class Meta(DeploymentSerializer.Meta):
        fields = DeploymentSerializer.Meta.fields + ["log"]