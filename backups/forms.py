from django import forms

from .models import BackupSettings


class BackupSettingsForm(forms.ModelForm):
    """Form to update backup configuration."""

    class Meta:
        model = BackupSettings
        fields = [
            "automatic_enabled",
            "scheduled_time",
            "retention_days",
            "notify_email",
            "include_media",
        ]
        widgets = {
            "scheduled_time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }


class ManualBackupForm(forms.Form):
    """Trigger a manual backup."""

    include_media = forms.BooleanField(
        required=False,
        help_text="Include media files (may take longer).",
    )


class RestoreBackupForm(forms.Form):
    """Select a backup record to restore."""

    backup_id = forms.IntegerField(widget=forms.HiddenInput())
    confirm = forms.BooleanField(
        required=True,
        label="I understand that restoring will overwrite the current database.",
    )










