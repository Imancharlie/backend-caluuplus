from django.core.management.base import BaseCommand

from api.timetable_ops import send_due_reminders


class Command(BaseCommand):
    help = "Send in-app reminders for scheduled classes that are about to start."

    def handle(self, *args, **options):
        sent = send_due_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} session reminder(s)."))
