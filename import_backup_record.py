import os
import django
 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()
 
from backups.models import BackupRecord
from pathlib import Path
 
file_path = 'backups_storage/db_backups/db-20260629-085005.sqlite3'
file = Path(file_path)
 
if file.exists():
    BackupRecord.objects.create(
        file_path=file_path,
        file_size=file.stat().st_size,
        backup_type='manual',
        status='success',
        notes='Legacy backup imported from disk'
    )
    print(f'Backup record created for {file_path}')
else:
    print(f'File not found: {file_path}')
 