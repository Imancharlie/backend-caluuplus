from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_user_onboarding_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='communitystory',
            name='comments_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='communitystory',
            name='purge_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='communitystory',
            name='kind',
            field=models.CharField(
                choices=[
                    ('question', 'Question'),
                    ('photo', 'Campus photo'),
                    ('learned', 'What I learned'),
                    ('competition', 'Competition'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='communitystory',
            index=models.Index(fields=['purge_at'], name='api_communi_purge_a_idx'),
        ),
    ]
