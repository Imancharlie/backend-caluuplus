#!/usr/bin/env python3
"""
Test personality notes functionality
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from chatbot.enhanced_service import EnhancedClaudeService
from chatbot.models import Conversation, Message, ChatHistory
from api.models import User

def test_personality_notes():
    """Test personality notes extraction and storage"""
    
    print("🧪 Testing Personality Notes Functionality...")
    
    # Create test user if not exists
    user, created = User.objects.get_or_create(
        username='test_user_personality',
        defaults={'email': 'test@example.com', 'display_name': 'Test User'}
    )
    
    # Create test conversation
    conversation = Conversation.objects.create(
        user=user,
        title="Personality Test Chat"
    )
    
    # Test messages with personal information
    test_messages = [
        "Hello, I'm John and I have a girlfriend named Sarah",
        "I like to study in the morning and I'm studying architecture",
        "Call me Boss and speak in Kiswahili please",
        "My family lives in Dar es Salaam and I have two sisters"
    ]
    
    service = EnhancedClaudeService()
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📝 Test {i}: '{message}'")
        
        try:
            # Get AI response
            response = service.get_enhanced_response(
                user_message=message,
                user=user,
                conversation=conversation
            )
            
            print(f"✅ Response: {response.text[:100]}...")
            print(f"📊 Tokens: {response.tokens_used}, Cost: {response.cost_tsh} TSH")
            print(f"🏷️  Topic: {response.current_topic}")
            print(f"👤 Personality Notes: {response.personality_notes}")
            print(f"⚙️  Instructions: {response.instructions}")
            
            # Save messages
            Message.objects.create(
                conversation=conversation,
                role="user",
                content=message
            )
            
            Message.objects.create(
                conversation=conversation,
                role="assistant",
                content=response.text,
                tokens_used=response.tokens_used,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_tsh=response.cost_tsh,
                topic=response.current_topic
            )
            
            # Update memory
            service.update_memory(user, conversation, response)
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    
    # Check final chat history
    chat_history = ChatHistory.objects.get(user=user)
    print(f"\n📋 Final Chat History:")
    print(f"Personality Notes: {chat_history.personality_notes}")
    print(f"Instructions: {chat_history.instructions}")
    print(f"Total Messages: {chat_history.total_messages}")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_personality_notes()



















