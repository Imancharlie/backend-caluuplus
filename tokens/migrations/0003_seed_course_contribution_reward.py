# Data migration: seed a RewardRule for course contributions so admins see and
# can configure the token amount. The amount below is a sensible default and is
# meant to be edited in the Django admin (Reward Rules).
from django.db import migrations


def forward(apps, schema_editor):
    RewardRule = apps.get_model('tokens', 'RewardRule')
    RewardRule.objects.update_or_create(
        key='COURSE_CONTRIBUTION',
        defaults={
            'label': 'Course Contribution',
            'amount': 5,
            'is_active': True,
            'description': (
                'Reward granted to a student each time they contribute a new '
                'course to the shared catalog for an academic year/semester '
                'that had no catalog entry.'
            ),
        },
    )


def backward(apps, schema_editor):
    RewardRule = apps.get_model('tokens', 'RewardRule')
    RewardRule.objects.filter(key='COURSE_CONTRIBUTION').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tokens', '0002_course_contribution'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
