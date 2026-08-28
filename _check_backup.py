import sqlite3
con = sqlite3.connect('backups_storage/db_backups/db-20260827-232457.sqlite3')
cur = con.cursor()
print('api_user has bio:', 'bio' in [r[1] for r in cur.execute('PRAGMA table_info(api_user)')])
print('api_user has tokens_balance:', 'tokens_balance' in [r[1] for r in cur.execute('PRAGMA table_info(api_user)')])
print('--- last api migrations recorded ---')
for r in cur.execute("SELECT name FROM django_migrations WHERE app='api' ORDER BY id DESC LIMIT 6"):
    print('  ', r[0])
print('--- apps present ---')
apps = [r[0] for r in cur.execute('SELECT DISTINCT app FROM django_migrations')]
print('  ', apps)
print('--- token tables? ---')
t = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tokens_%'")]
print('  ', t)
print('--- user count ---')
print('  ', cur.execute('SELECT COUNT(*) FROM api_user').fetchone()[0])
