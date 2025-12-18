from django.core.management.base import BaseCommand

from backups.models import BackupRecord
from backups.utils import perform_backup


class Command(BaseCommand):
    help = "Run the automated backup process."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-media",
            action="store_true",
            help="Include media files in the backup archive.",
        )

    def handle(self, *args, **options):
        include_media = options.get("include_media")
        record, error = perform_backup(
            backup_type=BackupRecord.BackupType.AUTOMATIC,
            include_media=include_media,
        )
        if error:
            self.stderr.write(self.style.ERROR(f"Backup failed: {error}"))
        else:
            self.stdout.write(self.style.SUCCESS("Backup completed successfully."))










