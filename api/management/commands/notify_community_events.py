from django.core.management.base import BaseCommand

from api.community import notify_due_community_events


class Command(BaseCommand):
    help = "Notify creators and participants when a challenge closes or results are released."

    def handle(self, *args, **options):
        sent = notify_due_community_events(force=True)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} community notification(s)."))
