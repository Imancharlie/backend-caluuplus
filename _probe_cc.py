import sqlite3
c = sqlite3.connect("db.sqlite3")
cur = c.cursor()
for t in ["api_articlecomment"]:
    try:
        rows = cur.execute(f"PRAGMA table_info({t})").fetchall()
        print(f"{t} columns:")
        for r in rows:
            print("  ", r[1], r[2], "notnull" if r[3] else "", "pk" if r[5] else "")
    except Exception as e:
        print(t, "ERR", e)
print("\nindexes:")
for r in cur.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='api_articlecomment'"):
    print(r[0], "->", r[1])
