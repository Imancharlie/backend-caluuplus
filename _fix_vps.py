import sqlite3, sys

con = sqlite3.connect('db.sqlite3')
cur = con.cursor()

api_stale = [
    '0016_universitylink',
    '0017_user_firebase_uid_user_profile_picture',
    '0018_user_hobbies',
    '0019_gpacalculation',
    '0020_loginactivity',
    '0021_remove_user_gender_user_is_student',
    '0022_remove_gpacalculation_gpa_gpacalculation_gpa_alg_and_more',
    '0023_user_last_seen_at_alter_gpacalculation_gpa_alg_and_more',
    '0024_articlelike_and_more',
]

api_add = [
    '0016_add_university_link',
    '0017_modify_university_link_model',
    '0018_user_firebase_uid_user_profile_picture',
    '0019_user_hobbies',
    '0020_gpacalculation',
    '0021_add_login_activity',
    '0022_remove_user_gender_user_is_student',
    '0023_backfill_article_category_general',
    '0024_encrypt_gpa_values_and_remove_plaintext',
    '0025_alter_gpacalculation_gpa_alg_and_more',
]

cur.execute("DELETE FROM django_migrations WHERE app='api' AND name IN (%s)"
            % ','.join('?'*len(api_stale)), api_stale)

next_id = cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM django_migrations").fetchone()[0]

def exists(app, name):
    return cur.execute("SELECT 1 FROM django_migrations WHERE app=? AND name=?", (app, name)).fetchone() is not None

def insert(app, name):
    global next_id
    if exists(app, name):
        return
    cur.execute("INSERT INTO django_migrations (id,app,name,applied) VALUES (?,?,?,?)",
                (next_id, app, name, '2026-01-01 00:00:00'))
    next_id += 1

for n in api_add:
    insert('api', n)

cur.execute("DELETE FROM django_migrations WHERE app='resources_opps' AND name='0002_alter_resource_university'")
insert('resources_opps', '0002_modify_resource_university_field')
insert('resources_opps', '0003_alter_opportunity_options_opportunity_is_active_and_more')

con.commit()

print('repaired OK')
print('pending api (not yet migrated):',
      [r[0] for r in cur.execute(
          "SELECT name FROM django_migrations WHERE app='api' AND name LIKE '002%' ORDER BY name")])
con.close()
