import sqlite3, json, collections

con = sqlite3.connect(r'C:\Users\ADMINI~1\AppData\Local\Temp\opencode\db_mig_test.sqlite3')
cur = con.cursor()
rows = cur.execute('SELECT id, courses FROM api_studentcourse').fetchall()

shapes = collections.Counter()
period_counts = collections.Counter()
sample_by_shape = {}

for sid, raw in rows:
    if raw is None:
        shapes['NULL'] += 1
        continue
    try:
        data = json.loads(raw)
    except Exception:
        shapes['BAD_JSON'] += 1
        continue
    if isinstance(data, list):
        shapes['list'] += 1
        sample_by_shape.setdefault('list', raw[:300])
        # count items with/without year
        ys = sum(1 for c in data if isinstance(c, dict) and c.get('year') is not None)
        period_counts['list items with year'] += ys
        period_counts['list total items'] += len(data)
    elif isinstance(data, dict):
        if 'periods' in data and isinstance(data['periods'], dict):
            shapes['periods_wrapper'] += 1
            sample_by_shape.setdefault('periods_wrapper', raw[:400])
            p = data['periods']
            period_counts['total periods'] += len(p)
            total_items = 0
            for k, v in p.items():
                if isinstance(v, list):
                    total_items += len(v)
            period_counts['total course items'] += total_items
        elif '_v' in data:
            shapes['other_dict'] += 1
            sample_by_shape.setdefault('other_dict', raw[:300])
        else:
            shapes['plain_dict'] += 1
            sample_by_shape.setdefault('plain_dict', raw[:300])
    else:
        shapes['other'] += 1

print('shape counts:')
for k, v in shapes.items():
    print('  %-16s %d' % (k, v))
print('period counts:', dict(period_counts))
print()
print('samples:')
for k, v in sample_by_shape.items():
    print('--- %s ---' % k)
    print(v)
    print()
con.close()
