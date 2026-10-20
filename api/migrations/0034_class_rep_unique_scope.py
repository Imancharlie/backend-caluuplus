from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0033_community_stories'),
    ]

    operations = [
        # 0032 declares this constraint. SQLite skipped the earlier nulls-distinct
        # version, so create the index when it is missing. Fresh databases that
        # already have it from 0032 are left unchanged.
        migrations.RunSQL(
            sql=(
                'CREATE UNIQUE INDEX IF NOT EXISTS uniq_class_rep_scope '
                'ON api_classrepresentative (user_id, program_id, cohort_year)'
            ),
            reverse_sql='DROP INDEX IF EXISTS uniq_class_rep_scope',
        ),
    ]
