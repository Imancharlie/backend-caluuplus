from django.db import migrations, models


def mark_existing_users_complete(apps, schema_editor):
    User = apps.get_model("api", "User")
    User.objects.all().update(onboarding_state={
        "social_seen": True,
        "interests_status": "legacy",
        "reminder_after": None,
        "dismiss_count": 0,
    })


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0035_community_story_card_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="onboarding_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Shared web/mobile onboarding progress. Empty means a new account still has steps pending.",
            ),
        ),
        migrations.RunPython(mark_existing_users_complete, migrations.RunPython.noop),
    ]
