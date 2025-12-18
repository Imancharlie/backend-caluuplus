from __future__ import annotations

import os
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import BackupRecord, BackupSettings

BACKUP_SUBDIR = "db_backups"
MEDIA_ARCHIVE_NAME = "media.tar.gz"


def _get_db_path() -> Path:
    db_config = settings.DATABASES.get("default", {})
    engine = db_config.get("ENGINE", "")
    name = db_config.get("NAME")
    if "sqlite" not in engine:
        raise NotImplementedError("Automated backups currently support SQLite databases only.")
    if not name:
        raise ValueError("Database NAME setting is missing.")
    return Path(name)


def _get_backup_root() -> Path:
    root = Path(getattr(settings, "BACKUP_ROOT", settings.BASE_DIR / "backups"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cleanup_old_backups(retention_days: int) -> None:
    cutoff = timezone.now() - timedelta(days=retention_days)
    stale_records = BackupRecord.objects.filter(created_at__lt=cutoff)
    for record in stale_records:
        try:
            path = Path(record.file_path)
            if path.exists():
                path.unlink()
        except Exception:
            pass
        record.delete()


def _create_media_archive(destination: Path) -> Optional[Path]:
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return None
    archive_path = destination / MEDIA_ARCHIVE_NAME
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(media_root, arcname="media")
    return archive_path


def perform_backup(
    *,
    user=None,
    backup_type: str = BackupRecord.BackupType.MANUAL,
    include_media: Optional[bool] = None,
    notify: bool = True,
) -> Tuple[Optional[BackupRecord], Optional[str]]:
    """Create a database (and optional media) backup."""

    settings_obj = BackupSettings.load()
    include_media = include_media if include_media is not None else settings_obj.include_media

    db_path = _get_db_path()
    backup_root = _get_backup_root() / BACKUP_SUBDIR
    backup_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    db_backup_name = f"db-{timestamp}{db_path.suffix or '.sqlite3'}"
    db_backup_path = backup_root / db_backup_name

    record = BackupRecord.objects.create(
        created_by=user,
        backup_type=backup_type,
        status=BackupRecord.BackupStatus.SUCCESS,
        file_path=str(db_backup_path),
    )

    start_time = timezone.now()
    try:
        shutil.copy2(db_path, db_backup_path)
        total_size = db_backup_path.stat().st_size
        media_archive_path = None
        if include_media:
            media_archive_path = _create_media_archive(backup_root)
            if media_archive_path and media_archive_path.exists():
                total_size += media_archive_path.stat().st_size
        duration = (timezone.now() - start_time).total_seconds()
        record.file_size = total_size
        record.duration_seconds = duration
        record.save(update_fields=["file_size", "duration_seconds"])

        _cleanup_old_backups(settings_obj.retention_days)

        if notify:
            _send_backup_email(record, settings_obj, include_media)

        return record, None
    except Exception as exc:  # noqa: BLE001
        record.status = BackupRecord.BackupStatus.FAILED
        record.notes = str(exc)
        record.save(update_fields=["status", "notes"])
        return None, str(exc)


def _send_backup_email(record: BackupRecord, settings_obj: BackupSettings, include_media: bool) -> None:
    recipient = settings_obj.effective_notify_email
    if not recipient:
        return

    subject = "CaluuPlus Backup Completed"
    size_mb = record.file_size / (1024 * 1024) if record.file_size else 0
    body_lines = [
        "Hello team,",
        "",
        "A new backup has been created successfully.",
        f"Type: {record.get_backup_type_display()}",
        f"Size: {size_mb:.2f} MB",
        f"Includes media: {'Yes' if include_media else 'No'}",
        f"Created at: {record.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "You can manage backups from the admin dashboard.",
    ]

    send_mail(
        subject,
        "\n".join(body_lines),
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@caluuplus.com"),
        [recipient],
        fail_silently=True,
    )


def restore_backup(record: BackupRecord, *, user=None) -> Tuple[bool, Optional[str]]:
    """Restore the database from a backup file."""

    db_path = _get_db_path()
    backup_file = Path(record.file_path)

    if not backup_file.exists():
        return False, "Backup file is missing."

    try:
        shutil.copy2(backup_file, db_path)
        record.mark_restored(user=user)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)










