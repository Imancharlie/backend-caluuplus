#!/usr/bin/env python3
"""
Test script to verify Mr. Caluu chatbot fixes
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

def test_chatbot_fixes():
    """Test the chatbot with various inputs to verify fixes"""
    
    print("🧪 Testing Mr. Caluu Chatbot Fixes...")
    
    # Create test user if not exists
    user, created = User.objects.get_or_create(
        username='test_user',
        defaults={'email': 'test@example.com', 'display_name': 'Test User'}
    )
    
    # Create test conversation
    conversation = Conversation.objects.create(
        user=user,
        title="Test Chat"
    )
    
    # Test cases
    test_cases = [
        "hello",
        "how to use autocad give me the shortcuts",
        "what's my schedule today?",
        "tell me about my courses"
    ]
    
    service = EnhancedClaudeService()
    
    for i, message in enumerate(test_cases, 1):
        print(f"\n📝 Test {i}: '{message}'")
        
        try:
            # Get response
            response = service.get_enhanced_response(
                user_message=message,
                user=user,
                conversation=conversation
            )
            
            print(f"✅ Response: {response.text[:100]}...")
            print(f"📊 Tokens: {response.tokens_used}, Cost: {response.cost_tsh} TSH")
            print(f"🏷️  Topic: {response.current_topic}")
            print(f"🔄 Topic Changed: {response.topic_changed}")
            
            # Save message
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
    
    # Test conversation summary
    print(f"\n📋 Conversation Summary:")
    print(f"Messages: {conversation.messages.count()}")
    print(f"Summary: {conversation.summary[:200] if conversation.summary else 'None'}...")
    
    # Test chat history
    chat_history, _ = ChatHistory.objects.get_or_create(user=user)
    print(f"\n👤 Chat History Stats:")
    print(f"Total Messages: {chat_history.total_messages}")
    print(f"Total Tokens: {chat_history.total_tokens}")
    print(f"Total Cost: {chat_history.total_cost_tsh} TSH")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_chatbot_fixes()



















