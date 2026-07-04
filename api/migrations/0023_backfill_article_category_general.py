from django.db import migrations, models


def backfill_article_category(apps, schema_editor):
    Article = apps.get_model('api', 'Article')
    Article.objects.filter(category__isnull=True).update(category='general')
    Article.objects.filter(category='').update(category='general')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_remove_user_gender_user_is_student'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='category',
            field=models.CharField(
                choices=[
                    ('academic', 'Academic'),
                    ('campus_life', 'Campus Life'),
                    ('news', 'News'),
                    ('events', 'Events'),
                    ('general', 'General'),
                ],
                default='general',
                max_length=50,
            ),
        ),
        migrations.RunPython(backfill_article_category, migrations.RunPython.noop),
    ]
