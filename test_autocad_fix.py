#!/usr/bin/env python3
"""
Test AutoCAD shortcuts fix
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

def test_autocad_shortcuts():
    """Test AutoCAD shortcuts quick response"""
    
    print("🧪 Testing AutoCAD Shortcuts Fix...")
    
    # Create test user if not exists
    user, created = User.objects.get_or_create(
        username='test_user',
        defaults={'email': 'test@example.com', 'display_name': 'Test User'}
    )
    
    # Create test conversation
    conversation = Conversation.objects.create(
        user=user,
        title="Test AutoCAD Chat"
    )
    
    service = EnhancedClaudeService()
    
    # Test AutoCAD shortcuts
    test_messages = [
        "i need autocad shortcuts",
        "give me autocad commands",
        "autocad shortcuts for house design",
        "hello",
        "what's my schedule today?"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📝 Test {i}: '{message}'")
        
        try:
            # Test quick response first
            quick_response = service.get_quick_response("autocad", user) if "autocad" in message.lower() else None
            
            if quick_response:
                print(f"✅ Quick Response: {quick_response[:100]}...")
            else:
                # Get AI response
                response = service.get_enhanced_response(
                    user_message=message,
                    user=user,
                    conversation=conversation
                )
                print(f"✅ AI Response: {response.text[:100]}...")
                print(f"📊 Tokens: {response.tokens_used}, Cost: {response.cost_tsh} TSH")
                print(f"🏷️  Topic: {response.current_topic}")
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_autocad_shortcuts()



















