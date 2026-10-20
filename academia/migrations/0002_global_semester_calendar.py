from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academia', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GlobalSemesterCalendar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester_1_start', models.DateField(blank=True, null=True)),
                ('semester_1_end', models.DateField(blank=True, null=True)),
                ('semester_2_start', models.DateField(blank=True, null=True)),
                ('semester_2_end', models.DateField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Semester dates (all universities)',
                'verbose_name_plural': 'Semester dates (all universities)',
            },
        ),
    ]
