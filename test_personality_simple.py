#!/usr/bin/env python3
"""
Simple test for personality notes
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from chatbot.enhanced_service import EnhancedClaudeService
from chatbot.models import Conversation, ChatHistory
from api.models import User

def test_simple_personality():
    """Simple test for personality notes extraction"""
    
    print("🧪 Testing Simple Personality Notes...")
    
    # Create test user
    user, created = User.objects.get_or_create(
        username='test_simple',
        defaults={'email': 'test@example.com', 'display_name': 'Test User'}
    )
    
    # Create conversation
    conversation = Conversation.objects.create(
        user=user,
        title="Simple Test"
    )
    
    service = EnhancedClaudeService()
    
    # Test personal info extraction
    test_message = "Hello, I have a girlfriend named Sarah and I like to study architecture"
    print(f"📝 Testing message: '{test_message}'")
    
    # Test personal info extraction
    personal_info = service._extract_personal_info_from_message(test_message)
    print(f"🔍 Extracted personal info: '{personal_info}'")
    
    # Test AI response
    try:
        response = service.get_enhanced_response(
            user_message=test_message,
            user=user,
            conversation=conversation
        )
        
        print(f"✅ AI Response: {response.text[:100]}...")
        print(f"👤 Personality Notes: {response.personality_notes}")
        print(f"⚙️  Instructions: {response.instructions}")
        
        # Update memory
        service.update_memory(user, conversation, response)
        
        # Check chat history
        chat_history = ChatHistory.objects.get(user=user)
        print(f"\n📋 Chat History:")
        print(f"Personality Notes: {chat_history.personality_notes}")
        print(f"Instructions: {chat_history.instructions}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_simple_personality()



















