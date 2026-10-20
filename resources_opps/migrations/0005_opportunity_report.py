import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('resources_opps', '0004_opportunity_general_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='OpportunityReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.CharField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('opportunity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='resources_opps.opportunity')),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opportunity_reports', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='opportunityreport',
            constraint=models.UniqueConstraint(fields=('opportunity', 'reporter'), name='unique_opportunity_report'),
        ),
    ]
