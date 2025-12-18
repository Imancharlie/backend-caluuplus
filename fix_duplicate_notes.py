#!/usr/bin/env python3
"""
Fix duplicate personality notes
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from chatbot.models import ChatHistory
from chatbot.enhanced_service import EnhancedClaudeService

def fix_duplicate_notes():
    """Fix duplicate personality notes"""
    
    print("🧹 Fixing duplicate personality notes...")
    
    service = EnhancedClaudeService()
    
    # Get all chat histories
    chat_histories = ChatHistory.objects.all()
    
    for chat_history in chat_histories:
        print(f"\n👤 User: {chat_history.user.username}")
        
        # Show current state
        if chat_history.personality_notes:
            print("📝 Current personality notes:")
            for i, line in enumerate(chat_history.personality_notes.split('\n'), 1):
                print(f"   {i}. {line}")
        
        # Clean the notes
        if chat_history.personality_notes:
            cleaned_notes = service._clean_personality_notes(chat_history.personality_notes)
            
            if cleaned_notes != chat_history.personality_notes:
                print("✨ After cleaning:")
                for i, line in enumerate(cleaned_notes.split('\n'), 1):
                    print(f"   {i}. {line}")
                
                # Save the cleaned version
                chat_history.personality_notes = cleaned_notes
                chat_history.save(update_fields=['personality_notes'])
                print("✅ Saved cleaned version")
            else:
                print("✅ No duplicates found")
        
        # Clean instructions too
        if chat_history.instructions:
            cleaned_instructions = service._clean_personality_notes(chat_history.instructions)
            
            if cleaned_instructions != chat_history.instructions:
                print("⚙️  Cleaned instructions:")
                for i, line in enumerate(cleaned_instructions.split('\n'), 1):
                    print(f"   {i}. {line}")
                
                chat_history.instructions = cleaned_instructions
                chat_history.save(update_fields=['instructions'])
                print("✅ Saved cleaned instructions")
    
    print("\n🎉 All duplicate notes have been cleaned!")

if __name__ == "__main__":
    fix_duplicate_notes()



















