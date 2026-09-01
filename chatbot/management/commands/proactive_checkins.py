from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta


class Command(BaseCommand):
    help = 'Generate proactive check-ins for students (run via cron).'

    def handle(self, *args, **options):
        from chatbot.models import Conversation, Message, StudentMemory
        from api.models import Student

        # Rate limit window: max 1 unsolicited check-in per student per 3 days
        rate_window_seconds = 3 * 24 * 3600

        # Find students who have been active in the last 2 days (open, non-stale threads)
        cutoff = timezone.now() - timedelta(days=2)
        active_user_ids = Conversation.objects.filter(
            updated_at__gte=cutoff,
            is_active=True,
            mode='bot',
        ).values_list('user_id', flat=True).distinct()

        sent_count = 0

        for user_id in active_user_ids:
            # Hard rate limit — never feel like spam or surveillance
            rate_key = f"checkin:{user_id}"
            if cache.get(rate_key):
                continue

            student = Student.objects.filter(user_id=user_id).first()
            if not student:
                continue

            # Only check in on students who have a stated stressor or goal (from memory)
            memories = StudentMemory.objects.filter(
                student=student,
                is_active=True,
                key__in=['stressor', 'goal'],
            )
            if not memories.exists():
                continue

            memory = memories.first()

            # Find the most recent open conversation
            convo = Conversation.objects.filter(
                user_id=user_id, is_active=True, mode='bot'
            ).order_by('-updated_at').first()
            if not convo:
                continue

            # Don't check in if the most recent message is already from Mr Caluu
            last_msg = convo.messages.order_by('-timestamp').first()
            if last_msg and last_msg.role == 'assistant':
                # Skip if an assistant message is the most recent (already a pending reply)
                continue

            # Personalized, memory-anchored check-in (structured trigger + persona tone)
            checkin_msg = (
                f"hey, been thinking about what you shared about "
                f"{memory.value.strip().lower()} — how's that going? "
                f"just checking in, no pressure 😊"
            )

            with cache:
                Message.objects.create(
                    conversation=convo,
                    role='assistant',
                    content=checkin_msg,
                    tokens_used=0,
                    cost_tsh=0.0,
                )
                convo.save(update_fields=['updated_at'])

                # Rate limit for 3 days
                cache.set(rate_key, True, timeout=rate_window_seconds)

            sent_count += 1
            self.stdout.write(f"Check-in sent to user {user_id}")

        self.stdout.write(self.style.SUCCESS(f"Proactive check-ins completed: {sent_count} sent"))
