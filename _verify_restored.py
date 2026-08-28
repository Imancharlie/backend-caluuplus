import sqlite3
con = sqlite3.connect('db.sqlite3')
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print('tokens tables:', [t for t in tables if t.startswith('tokens_')])
print('caluu_map tables:', [t for t in tables if t.startswith('caluu_map_')])
for tbl in ('api_user', 'api_universitylink', 'api_gpacalculation', 'resources_opps_opportunity'):
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info({tbl})')]
    print(f'{tbl}: column count={len(cols)}')
    print('  ', cols)
print('users:', cur.execute('SELECT COUNT(*) FROM api_user').fetchone()[0])
