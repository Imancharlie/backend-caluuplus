from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0034_class_rep_unique_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='communitystory',
            name='card_color',
            field=models.CharField(blank=True, default='navy', max_length=20),
        ),
    ]
