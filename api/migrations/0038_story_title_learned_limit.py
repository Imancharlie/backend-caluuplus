from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_story_learned_and_photo_keep'),
    ]

    operations = [
        migrations.AlterField(
            model_name='communitystory',
            name='title',
            field=models.CharField(max_length=400),
        ),
    ]
