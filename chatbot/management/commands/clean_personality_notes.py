from django.core.management.base import BaseCommand
from chatbot.models import ChatHistory
from chatbot.enhanced_service import EnhancedClaudeService

class Command(BaseCommand):
    help = 'Clean up duplicate personality notes and instructions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        service = EnhancedClaudeService()
        
        self.stdout.write("🧹 Cleaning up personality notes and instructions...")
        
        chat_histories = ChatHistory.objects.all()
        cleaned_count = 0
        
        for chat_history in chat_histories:
            original_personality = chat_history.personality_notes
            original_instructions = chat_history.instructions
            
            # Clean personality notes
            if original_personality:
                cleaned_personality = service._clean_personality_notes(original_personality)
                if cleaned_personality != original_personality:
                    self.stdout.write(f"👤 User: {chat_history.user.username}")
                    self.stdout.write(f"   Before: {len(original_personality.split('•')) - 1} personality notes")
                    self.stdout.write(f"   After:  {len(cleaned_personality.split('•')) - 1} personality notes")
                    
                    if not dry_run:
                        chat_history.personality_notes = cleaned_personality
                        chat_history.save(update_fields=['personality_notes'])
                    
                    cleaned_count += 1
            
            # Clean instructions
            if original_instructions:
                cleaned_instructions = service._clean_personality_notes(original_instructions)
                if cleaned_instructions != original_instructions:
                    self.stdout.write(f"⚙️  User: {chat_history.user.username}")
                    self.stdout.write(f"   Before: {len(original_instructions.split('•')) - 1} instructions")
                    self.stdout.write(f"   After:  {len(cleaned_instructions.split('•')) - 1} instructions")
                    
                    if not dry_run:
                        chat_history.instructions = cleaned_instructions
                        chat_history.save(update_fields=['instructions'])
                    
                    cleaned_count += 1
        
        if dry_run:
            self.stdout.write(f"🔍 Would clean {cleaned_count} chat histories")
        else:
            self.stdout.write(f"✅ Cleaned {cleaned_count} chat histories")



















