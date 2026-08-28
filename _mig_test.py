import os, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
import sqlite3

SCRATCH = r'C:\Users\ADMINI~1\AppData\Local\Temp\opencode\db_mig_test.sqlite3'

# pre-inspect
con = sqlite3.connect(SCRATCH)
cur = con.cursor()
print('BEFORE  migrations:', [r[0] for r in cur.execute("SELECT name FROM django_migrations WHERE app='api' ORDER BY id DESC LIMIT 3")])
print('BEFORE  studentcourse rows:', cur.execute('SELECT COUNT(*) FROM api_studentcourse').fetchone()[0])
print('BEFORE  sample json:', cur.execute('SELECT courses FROM api_studentcourse LIMIT 1').fetchone()[0][:200])
con.close()

# Point Django at the scratch DB and run migrations programmatically.
import django.conf
django.setup()

from django.conf import settings
settings.DATABASES['default']['NAME'] = SCRATCH

from django.core.management import call_command
print('--- running migrate ---')
call_command('migrate', 'api', verbosity=1)

# post-inspect
con = sqlite3.connect(SCRATCH)
cur = con.cursor()
print('AFTER   migrations:', [r[0] for r in cur.execute("SELECT name FROM django_migrations WHERE app='api' ORDER BY id DESC LIMIT 3")])
print('AFTER   terms:', cur.execute('SELECT COUNT(*) FROM api_studentterm').fetchone()[0])
print('AFTER   enrollments:', cur.execute('SELECT COUNT(*) FROM api_studentcourseenrollment').fetchone()[0])
print('AFTER   sample enrollments:')
for r in cur.execute('SELECT academic_year, semester, code, name, credits, type, course_id FROM api_studentterm t JOIN api_studentcourseenrollment e ON e.term_id=t.id LIMIT 6'):
    print('   ', r)
con.close()
print('DONE')
