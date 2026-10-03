"""Backup retention must bound disk usage, not just age.

The auto-deploy snapshots the database on every run. With a 60-second timer that
produced 1440 snapshots a day, all sharing one ``created_at`` date, so pruning by
``retention_days`` removed nothing until the next day -- by which time a
multi-megabyte database had filled the disk. ``BACKUP_MAX_COUNT`` caps the
retained set so the total is bounded no matter how often backups are taken.
"""
from django.test import TestCase

from backups.models import BackupRecord
from backups.utils import _cleanup_old_backups


class BackupRetentionTests(TestCase):
    def _make_record(self, name):
        return BackupRecord.objects.create(
            file_path=f"/tmp/{name}.sqlite3",
            file_size=1024,
            status=BackupRecord.BackupStatus.SUCCESS,
        )

    def test_count_cap_prunes_the_surplus(self):
        records = [self._make_record(f"b{i}") for i in range(10)]
        # Oldest first is the default ordering, so the last one is newest.
        _cleanup_old_backups(retention_days=14, max_count=3)
        self.assertEqual(BackupRecord.objects.count(), 3)
        self.assertTrue(
            BackupRecord.objects.filter(pk=records[-1].pk).exists(),
            "the newest snapshot must survive",
        )

    def test_keeps_newest_and_drops_oldest(self):
        old = [self._make_record(f"old{i}") for i in range(4)]
        new = [self._make_record(f"new{i}") for i in range(3)]
        _cleanup_old_backups(retention_days=14, max_count=3)
        survivors = set(BackupRecord.objects.values_list("pk", flat=True))
        self.assertEqual(survivors, {r.pk for r in new})
        for record in old:
            self.assertNotIn(record.pk, survivors)

    def test_no_cap_configured_keeps_everything(self):
        for i in range(6):
            self._make_record(f"keep{i}")
        _cleanup_old_backups(retention_days=14, max_count=0)
        self.assertEqual(BackupRecord.objects.count(), 6)

    def test_age_still_prunes_when_under_the_cap(self):
        from datetime import timedelta

        from django.utils import timezone

        stale = self._make_record("ancient")
        BackupRecord.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=90)
        )
        self._make_record("fresh")
        _cleanup_old_backups(retention_days=14, max_count=50)
        self.assertEqual(BackupRecord.objects.count(), 1)
        self.assertFalse(BackupRecord.objects.filter(pk=stale.pk).exists())

    def test_unlink_is_attempted_only_for_existing_files(self):
        """A record whose file is already gone must still be pruned, not raise."""
        # Created first, so it is the older one and therefore the surplus.
        missing = self._make_record("missing-on-disk")
        self._make_record("still-here")
        _cleanup_old_backups(retention_days=14, max_count=1)
        self.assertFalse(
            BackupRecord.objects.filter(pk=missing.pk).exists(),
            "a record with no file on disk must still be removed",
        )


class MaxCountSettingTests(TestCase):
    """The cap must be wired up, not just implemented."""

    def test_settings_expose_a_sane_default(self):
        from django.conf import settings

        self.assertGreater(
            int(getattr(settings, "BACKUP_MAX_COUNT", 0)), 0,
            "BACKUP_MAX_COUNT must be configured",
        )

    def test_cleanup_reads_the_cap_from_settings_when_not_passed(self):
        from django.conf import settings

        from backups import utils

        for i in range(int(settings.BACKUP_MAX_COUNT) + 4):
            BackupRecord.objects.create(
                file_path=f"/tmp/wire{i}.sqlite3",
                status=BackupRecord.BackupStatus.SUCCESS,
            )
        # No max_count argument: it must fall back to the setting, not to None.
        utils._cleanup_old_backups(retention_days=365)
        self.assertEqual(
            BackupRecord.objects.count(), int(settings.BACKUP_MAX_COUNT)
        )