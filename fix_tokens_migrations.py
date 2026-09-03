"""Remove tokens migration records to allow re-running migrations."""

import sqlite3

# Connect to the database
con = sqlite3.connect('db.sqlite3')
cur = con.cursor()

# Delete all tokens migration records
cur.execute("DELETE FROM django_migrations WHERE app='tokens'")
con.commit()

print("Deleted tokens migration records from django_migrations")

# Verify
cur.execute("SELECT name FROM django_migrations WHERE app='tokens'")
remaining = cur.fetchall()
print(f"Remaining tokens migrations: {len(remaining)}")

con.close()
