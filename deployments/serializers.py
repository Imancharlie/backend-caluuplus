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