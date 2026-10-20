"""Set the feature prices and rewards, then give every current user the welcome grant once."""
from django.db import migrations


REWARD_RULES = [
    (
        "ARTICLE_SHARE_REWARD",
        "Article Share Reward",
        70,
        "Tokens given once when a person shares an article. Turn off to stop the payout.",
    ),
    (
        "OPPORTUNITY_SHARE",
        "Opportunity Shared",
        25,
        "Tokens given once when a person posts an opportunity. Turn off to stop the payout.",
    ),
    (
        "STORY_SHARE",
        "Story Shared",
        10,
        "Tokens given once when a person posts a story. Turn off to stop the payout.",
    ),
    (
        "MAP_LOCATION_ADDED",
        "Map Location Added",
        25,
        "Tokens given once when a person adds a place or venue on Caluu Map. Turn off to stop the payout.",
    ),
    (
        "SIGNUP_BONUS",
        "New Account Welcome",
        100,
        "Tokens given once to a new account. Turn off to stop welcoming new accounts.",
    ),
]

CONSUMPTION_RULES = [
    (
        "GPA_CALCULATION",
        "GPA Calculation",
        5,
        "Tokens required for one GPA calculation. Turn off to make GPA free.",
    ),
    (
        "MR_CALUU_MESSAGE",
        "Mr Caluu Message",
        10,
        "Tokens required for one Mr Caluu reply. Turn off to make chat free.",
    ),
    (
        "MAP_NAVIGATION",
        "Map Navigation",
        2,
        "Tokens required to start walking directions. Turn off to make directions free.",
    ),
]


def forward(apps, schema_editor):
    RewardRule = apps.get_model("tokens", "RewardRule")
    ConsumptionRule = apps.get_model("tokens", "ConsumptionRule")

    for key, label, amount, description in REWARD_RULES:
        rule = RewardRule.objects.filter(key=key).first()
        if rule is None:
            RewardRule.objects.create(
                key=key, label=label, amount=amount, is_active=True, description=description
            )
        else:
            rule.amount = amount
            rule.label = label
            rule.description = description
            rule.save(update_fields=["amount", "label", "description", "updated_at"])

    for key, label, amount, description in CONSUMPTION_RULES:
        rule = ConsumptionRule.objects.filter(key=key).first()
        if rule is None:
            ConsumptionRule.objects.create(
                key=key, label=label, amount=amount, is_active=True, description=description
            )
        else:
            rule.amount = amount
            rule.label = label
            rule.description = description
            rule.is_active = True
            rule.save(update_fields=["amount", "label", "description", "is_active", "updated_at"])

    from django.contrib.auth import get_user_model

    from tokens.services import grant_signup_bonus

    User = get_user_model()
    for user in User.objects.all().iterator():
        grant_signup_bonus(user)


def backward(apps, schema_editor):
    RewardRule = apps.get_model("tokens", "RewardRule")
    ConsumptionRule = apps.get_model("tokens", "ConsumptionRule")
    RewardRule.objects.filter(
        key__in=["OPPORTUNITY_SHARE", "STORY_SHARE", "MAP_LOCATION_ADDED", "SIGNUP_BONUS"]
    ).delete()
    ConsumptionRule.objects.filter(key="MAP_NAVIGATION").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0004_purchase_request"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
