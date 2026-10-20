from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources_opps', '0003_alter_opportunity_options_opportunity_is_active_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opportunity',
            name='category',
            field=models.CharField(
                choices=[
                    ('general', 'General'),
                    ('seminar', 'Seminar'),
                    ('competition', 'Competition'),
                    ('job', 'Job'),
                    ('meeting', 'Meeting'),
                    ('scholarship', 'Scholarship'),
                    ('internship', 'Internship'),
                    ('online_course', 'Online Course'),
                ],
                max_length=50,
            ),
        ),
    ]
