"""Seed the default token economy rules and packages."""
from django.core.management.base import BaseCommand

from tokens.models import (
    ConsumptionRule,
    RewardRule,
    TokenEconomyConfig,
    TokenPackage,
)


class Command(BaseCommand):
    help = "Seed default token economy reward/consumption rules and packages."

    def handle(self, *args, **options):
        reward_rules = [
            ("PROFILE_COMPLETION", "Profile Completion", 50, True),
            ("OPPORTUNITY_APPROVED", "Opportunity Approved", 20, True),
            ("ARTICLE_APPROVED", "Article Approved", 30, True),
            ("ARTICLE_SHARE_REWARD", "Article Share Reward", 2, True),
            ("SURVEY_COMPLETION", "Survey Completion", 10, True),
            ("SURVEY_QUESTION", "Survey Question Answered", 2, True),
            ("REFERRAL_COMPLETED", "Successful Referral", 100, True),
        ]
        for key, label, amount, active in reward_rules:
            _, created = RewardRule.objects.get_or_create(
                key=key, defaults={"label": label, "amount": amount, "is_active": active}
            )
            if created:
                self.stdout.write(f"  reward rule: {key} ({amount})")

        consume_rules = [
            ("GPA_CALCULATION", "GPA Calculation", 5, True),
            ("MR_CALUU_MESSAGE", "Mr Caluu Message", 3, True),
            ("MAP_ACTIVITY", "Map Activity", 2, True),
        ]
        for key, label, amount, active in consume_rules:
            _, created = ConsumptionRule.objects.get_or_create(
                key=key, defaults={"label": label, "amount": amount, "is_active": active}
            )
            if created:
                self.stdout.write(f"  consume rule: {key} ({amount})")

        packages = [
            ("Starter", 100, 5000.00, "TSH"),
            ("Booster", 500, 20000.00, "TSH"),
            ("Pro", 1200, 40000.00, "TSH"),
        ]
        for name, tokens, price, currency in packages:
            obj, created = TokenPackage.objects.get_or_create(
                name=name,
                defaults={"token_amount": tokens, "price_amount": price, "currency": currency},
            )
            if created:
                self.stdout.write(f"  package: {name} ({tokens} tokens)")

        TokenEconomyConfig.objects.get_or_create(
            key="REDEMPTION",
            defaults={"value": {"enabled": True, "minimum_amount": 500, "limits": {}}},
        )
        TokenEconomyConfig.objects.get_or_create(
            key="REFERRAL_REQUIRED_STATE",
            defaults={"value": {"registration": True, "phone_verified": True, "profile_complete": True}},
        )

        self.stdout.write(self.style.SUCCESS("Token economy seeded."))
