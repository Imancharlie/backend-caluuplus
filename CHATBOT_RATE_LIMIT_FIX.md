# Chatbot Fallback Response Fix

## Problem Diagnosis
After a few messages, the chatbot returns fallback responses like:
- "I'm currently at my usage limit..."
- "I'm having trouble connecting..."

## Root Cause
**Anthropic API Rate Limiting** - Sending messages too quickly triggers rate limits.

## Solutions (in order of recommendation)

### Solution 1: Request Higher Rate Limits (Recommended)
Contact Anthropic to increase your rate limits:
- Free tier: 5 requests/minute
- Paid tier: 50+ requests/minute
- Enterprise: Custom limits

**How to request:**
1. Go to https://console.anthropic.com
2. Navigate to Settings → Usage & Billing
3. Request rate limit increase

### Solution 2: Implement Smart Request Throttling
Add a delay between requests to stay under rate limits.

Add to `enhanced_service.py`:

```python
import time
from datetime import datetime, timedelta

class EnhancedClaudeService:
    def __init__(self):
        # ... existing code ...
        self._last_request_time = None
        self._min_request_interval = 12  # 12 seconds = 5 req/min (free tier)
    
    def get_enhanced_response(self, user_message: str, user, conversation, rag_context: str = ""):
        # Throttle requests to respect rate limits
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            if elapsed < self._min_request_interval:
                wait_time = self._min_request_interval - elapsed
                logger.info(f"Throttling request, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
        
        self._last_request_time = datetime.now()
        
        # ... rest of existing code ...
```

### Solution 3: Increase Timeout
For longer conversations, increase timeout from 30s to 60s:

```python
timeout_seconds = 60  # Instead of 30
```

### Solution 4: Better Retry Strategy
Increase retry attempts and backoff times:

```python
max_retries = 5  # Instead of 3
wait_time = (3 ** attempt)  # 3s, 9s, 27s instead of 1s, 2s, 4s
```

### Solution 5: Implement Request Queue
For high-volume usage, implement a request queue:

```python
from queue import Queue
from threading import Thread

class RequestQueue:
    def __init__(self, requests_per_minute=5):
        self.queue = Queue()
        self.interval = 60 / requests_per_minute
        self.worker = Thread(target=self._process_queue, daemon=True)
        self.worker.start()
    
    def _process_queue(self):
        while True:
            if not self.queue.empty():
                callback, args = self.queue.get()
                callback(*args)
                time.sleep(self.interval)
```

## Quick Check: What's Your Current Rate Limit?

Run this diagnostic:

```python
# In Django shell or test script
from chatbot.enhanced_service import EnhancedClaudeService
import time

service = EnhancedClaudeService()

# Send 10 requests rapidly and count failures
failures = 0
for i in range(10):
    try:
        # Test with a simple conversation
        result = service.get_enhanced_response(
            f"Test message {i}",
            user,
            conversation,
            ""
        )
        if "usage limit" in result.text.lower():
            failures += 1
        print(f"Request {i+1}: {'FAILED' if failures > 0 else 'SUCCESS'}")
        time.sleep(0.5)  # 0.5s between requests
    except Exception as e:
        failures += 1
        print(f"Request {i+1}: ERROR - {str(e)[:50]}")

print(f"\nRate Limit Test: {failures}/10 requests failed")
if failures > 3:
    print("DIAGNOSIS: Rate limiting detected. Apply Solution 1 or 2.")
```

## Monitoring

Add this to track rate limit hits:

```python
# In enhanced_service.py, line 392
logger.warning(f"RATE LIMIT HIT for user {user.id} - Consider upgrading API tier")

# Send alert email/notification to admin
from django.core.mail import mail_admins
mail_admins(
    "Chatbot Rate Limit Hit",
    f"User {user.id} hit rate limit. Consider upgrading Anthropic tier."
)
```

## Prevention: Optimize Further

1. **Use caching more aggressively:**
   ```python
   cache.set(cache_key, cache_data, 7200)  # 2 hours instead of 1
   ```

2. **Expand quick responses:**
   - More queries handled without API calls
   - Save ~200 tokens per quick response

3. **Implement conversation pausing:**
   - If 3+ messages in 1 minute, show: "Let me process that... (avoiding rate limits)"
   - Auto-resume after delay

## Expected Results

After applying Solution 1 or 2:
- ✅ No more fallback responses after a few messages
- ✅ Smooth conversation flow
- ✅ Better user experience
- ✅ Predictable costs

## Notes

- Free tier: 5 requests/min = 1 request every 12 seconds
- With caching (20% hit rate), effective limit becomes 6.25 req/min
- Paid tier removes most concerns (50+ req/min)

