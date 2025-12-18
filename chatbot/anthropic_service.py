from django.conf import settings
from anthropic import Anthropic


class AnthropicService:
    """Basic Anthropic API service wrapper"""
    
    def __init__(self):
        # Try multiple ways to get the API key
        api_key = None

        # Method 1: Check Django settings
        if hasattr(settings, 'ANTHROPIC_API_KEY'):
            api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)

        # Method 2: Check environment variable
        if not api_key:
            import os
            api_key = os.getenv('ANTHROPIC_API_KEY')

        # Method 3: Check settings with different case
        if not api_key and hasattr(settings, 'anthropic_api_key'):
            api_key = getattr(settings, 'anthropic_api_key', None)

        if not api_key:
            raise RuntimeError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY in Django settings or as an environment variable."
            )

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-haiku-20240307"
    
    def get_response(self, message: str, system_prompt: str = "") -> str:
        """Get a simple response from Claude"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.2,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": message
                }]
            )
            
            # Extract text from response
            text_parts = []
            for block in response.content:
                if getattr(block, "type", "") == "text":
                    text_parts.append(getattr(block, "text", ""))
            
            return "".join(text_parts) or "Sorry, I couldn't generate a response."
            
        except Exception as e:
            return f"Sorry, I'm having trouble connecting right now. Error: {str(e)[:100]}"







