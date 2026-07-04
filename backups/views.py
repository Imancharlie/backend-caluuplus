from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .forms import BackupSettingsForm, ManualBackupForm, RestoreBackupForm
from .models import BackupRecord, BackupSettings
from .utils import perform_backup, restore_backup


class AdminRequiredMixin(UserPassesTestMixin):
    """Allow only superusers."""

    def test_func(self):
        user = self.request.user
        return user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to access backups. Only superusers can access this page.")
        return redirect("/login")


class BackupDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Display and manage backups."""

    template_name = "backups/dashboard.html"
    success_url = reverse_lazy("backups:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings_obj = BackupSettings.load()
        context.update(
            {
                "settings_form": BackupSettingsForm(instance=settings_obj),
                "manual_backup_form": ManualBackupForm(initial={"include_media": settings_obj.include_media}),
                "records": BackupRecord.objects.all(),
                "settings_obj": settings_obj,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        if "trigger_backup" in request.POST:
            manual_form = ManualBackupForm(request.POST)
            if manual_form.is_valid():
                include_media = manual_form.cleaned_data["include_media"]
                record, error = perform_backup(
                    user=request.user,
                    backup_type=BackupRecord.BackupType.MANUAL,
                    include_media=include_media,
                )
                if error:
                    messages.error(request, f"Backup failed: {error}")
                else:
                    messages.success(request, "Backup completed successfully.")
            else:
                messages.error(request, "Invalid backup request.")
            return redirect(self.success_url)

        if "update_settings" in request.POST:
            settings_obj = BackupSettings.load()
            form = BackupSettingsForm(request.POST, instance=settings_obj)
            if form.is_valid():
                form.save()
                messages.success(request, "Backup settings updated.")
            else:
                messages.error(request, "Could not update settings. Please correct the errors.")
            return redirect(self.success_url)

        if "restore_backup" in request.POST:
            restore_form = RestoreBackupForm(request.POST)
            if restore_form.is_valid():
                backup_id = restore_form.cleaned_data["backup_id"]
                record = get_object_or_404(BackupRecord, id=backup_id)
                success, error = restore_backup(record, user=request.user)
                if success:
                    messages.success(request, "Backup restored. Restart the application to apply changes.")
                else:
                    messages.error(request, f"Restore failed: {error}")
            else:
                messages.error(request, "Invalid restore request.")
            return redirect(self.success_url)

        messages.error(request, "Unknown action.")
        return redirect(self.success_url)
