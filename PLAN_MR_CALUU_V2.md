# Mr Caluu v2 — Implementation Plan

> **Status**: Ready to implement
> **Base**: Django 5.2 + SQLite + Anthropic/Gemini AI + Token system
> **Infra additions**: django-redis (cache + rate limiter), management command + cron (no Celery)

---

## Current State Summary

| Component | Status | Notes |
|---|---|---|
| Chatbot views/services | ✅ Exists | `chatbot/views.py`, `chatbot/enhanced_service.py` |
| RAG vector search | ✅ Exists | `chatbot/vector_service.py` — keyword + optional semantic |
| Token system | ✅ Exists | `tokens/services.py` with consume/reward/purchase |
| AI providers | ✅ Exists | Gemini preferred, Anthropic fallback |
| Redis/Cache | ❌ Missing | No CACHES setting, using LocMemCache |
| SSE streaming | ❌ Missing | Blocking request-response |
| Persona module | ❌ Missing | Prompt built inline in `enhanced_service.py` |
| StudentMemory | ❌ Missing | Only `ChatHistory.personality_notes` (unstructured text) |
| Admin co-pilot | ❌ Missing | No conversation mode field |
| Content awareness | ⚠️ Partial | `Article` and `Opportunity` models exist but not in RAG |
| Scheduled jobs | ❌ Missing | No Celery, no cron, no management commands for jobs |
| File upload in chat | ❌ Missing | No attachment handling |

---

## Phase 1 — Foundational Fixes

### A1: Redis-based Rate Limiting

**Files to modify:**
- `requirements.txt` — add `django-redis>=5.4.0`, `redis>=5.0.0`
- `academic_backend/settings.py` — add `CACHES` config with Redis
- `chatbot/enhanced_service.py` — replace `time.sleep` throttle with Redis INCR+TTL

**What to do:**

1. Add to `requirements.txt`:
   ```
   django-redis>=5.4.0
   redis>=5.0.0
   ```

2. In `academic_backend/settings.py`, add CACHES:
   ```python
   import os

   CACHES = {
       "default": {
           "BACKEND": "django_redis.cache.RedisCache",
           "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
           "OPTIONS": {
               "CLIENT_CLASS": "django_redis.client.DefaultClient",
           },
           "TIMEOUT": 300,  # default 5 min
       }
   }
   ```

3. In `chatbot/enhanced_service.py`, replace `_throttle_request` (lines 661-680):
   ```python
   def _throttle_request(self, user_id) -> None:
       from django.core.cache import cache
       cache_key = f"throttle:user:{user_id}"
       count = cache.get(cache_key, 0)
       if count >= 1:  # max 1 request per interval
           raise ThrottledError("You're sending messages too fast. Please wait a moment.")
       cache.set(cache_key, count + 1, timeout=int(self._min_request_interval))
   ```
   - Remove `time.sleep(wait_time)` entirely
   - The existing `_throttle_request` at `enhanced_service.py:661` uses `time.sleep` — delete that
   - The retry `time.sleep` in `views.py:266` is for DB lock retries — keep that, it's correct

### A2: Kill Raw-JSON Leak

**Files to modify:**
- `chatbot/enhanced_service.py` — `_validate_response_schema` + reply extraction

**What to do:**

In `get_enhanced_response` (around line 888-906), add a guaranteed clean-text fallback AFTER JSON parsing:

```python
# After line 906 (reply = reply.strip()), add:
reply = self._ensure_clean_text(reply)

# New method:
def _ensure_clean_text(self, text: str) -> str:
    """Guarantee the reply is never raw JSON — always human-readable text."""
    if not text:
        return "I'm having a little trouble finding the right words. Could you rephrase that?"
    
    stripped = text.strip()
    
    # If it starts with { it's likely JSON leaked through
    if stripped.startswith('{') and '}' in stripped:
        try:
            import json
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and 'reply' in parsed:
                return parsed['reply']
            else:
                return "I'm having a little trouble with my response. Could you try again?"
        except (json.JSONDecodeError, ValueError):
            pass
    
    # Remove any remaining JSON artifacts
    cleaned = re.sub(r'^[\{\[].*?"reply"\s*:\s*"', '', stripped)
    cleaned = re.sub(r'",?\s*"current_topic".*[\}\]]$', '', cleaned)
    cleaned = cleaned.strip()
    
    if not cleaned or len(cleaned) < 3:
        return "I'm having a little trouble with my response. Could you try again?"
    
    return cleaned
```

### A7: Move API Keys to Environment Variables

**Files to modify:**
- `academic_backend/settings.py` — line 165, 169: replace hardcoded keys with `os.getenv` only (no fallback to literal key)
- `.env.example` — add the new vars

**What to do:**

In `settings.py`, change:
```python
# BEFORE (line 165):
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6IO...")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-api03-...")

# AFTER:
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
```

In `.env.example`, add:
```
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
REDIS_URL=redis://127.0.0.1:6379/1
```

### A3: Cache `build_student_context` in Redis

**Files to modify:**
- `chatbot/enhanced_service.py` — `build_student_context` method (line 158)

**What to do:**

```python
def build_student_context(self, user) -> str:
    from django.core.cache import cache
    cache_key = f"student_ctx:{user.id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # ... existing logic (lines 158-220) ...
    
    result = "\n".join(lines)
    cache.set(cache_key, result, timeout=300)  # 5 min TTL
    return result
```

Also, at the top of `get_enhanced_response`, cache the service instances instead of reconstructing per request:
- The `EnhancedClaudeService()` constructor already initializes the client once; the view creates it per-request at `views.py:139`. This is fine for now since the constructor is lightweight (just sets API key + client). No change needed here.

### A4: Move RAG + LLM Call Outside `transaction.atomic()`

**Files to modify:**
- `chatbot/views.py` — `send_message` method (lines 94-306)

**What to do:**

The current code wraps EVERYTHING in `transaction.atomic()` (line 130), including the LLM call. Refactor to:

```python
@action(detail=True, methods=["post"], url_path="send_message")
def send_message(self, request, pk=None):
    start_time = time.time()
    conversation = self.get_object()
    
    # Validate + sanitize input (no DB writes yet)
    raw_message = request.data.get("message", "")
    if not self._validate_and_sanitize_input(raw_message):
        return Response({"detail": "Invalid message format"}, status=400)
    
    sanitized_message = self._sanitize_message(raw_message)
    if not sanitized_message:
        return Response({"detail": "Message cannot be empty"}, status=400)
    
    # Check token balance BEFORE any LLM work (Phase 1 + token safety)
    # [Will be added in Phase 3, but structure for it now]
    
    # Save user message (short transaction, no LLM)
    with transaction.atomic():
        user_msg = Message.objects.create(
            conversation=conversation,
            role="user",
            content=sanitized_message
        )
    
    # --- LLM work happens OUTSIDE transaction ---
    enhanced_service = EnhancedClaudeService()
    vector_service = VectorSearchService()
    
    quick = None
    ai_response = None
    assistant_msg = None
    
    # Quick response path (no API call)
    message_count = conversation.messages.count()
    quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)
    
    if quick_type:
        quick = enhanced_service.get_quick_response(quick_type, request.user)
        if quick:
            with transaction.atomic():
                assistant_msg = Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=quick,
                    tokens_used=0,
                    cost_tsh=0.0
                )
    else:
        # RAG search (no DB write)
        rag_context = ""
        navigation_context = ""
        try:
            # ... existing RAG search logic ...
            pass
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
        
        # LLM call (no DB write)
        ai_response = enhanced_service.get_enhanced_response(
            sanitized_message, request.user, conversation,
            rag_context, navigation_context
        )
        
        # Save response (short transaction)
        with transaction.atomic():
            assistant_msg = Message.objects.create(
                conversation=conversation,
                role="assistant",
                content=ai_response.text,
                tokens_used=ai_response.tokens_used,
                cost_tsh=ai_response.cost_tsh
            )
            conversation.save(update_fields=["updated_at"])
    
    # Memory update (separate, best-effort)
    if ai_response is not None:
        try:
            enhanced_service.update_memory(request.user, conversation, ai_response)
        except Exception as e:
            logger.error(f"Memory update failed: {e}")
    
    # Token consumption (separate)
    try:
        from tokens import services as token_service
        token_service.consume(
            request.user, "MR_CALUU_MESSAGE",
            reference_key=f"mrcaluu:{assistant_msg.id}" if assistant_msg else None,
            description="Mr Caluu message",
            initiated_by="chatbot",
        )
    except Exception as e:
        logger.warning(f"Token consumption skipped: {e}")
    
    serializer = ConversationSerializer(conversation)
    return Response(serializer.data)
```

Key changes:
- Each `transaction.atomic()` block is now short-lived (just DB writes)
- LLM call + RAG search happen between transactions
- Remove the retry loop with `time.sleep` for DB locks (the retry was covering the fact that LLM was inside the transaction)

### A5: Configure Redis as Real Cache Backend

Already done in A1 above. The CACHES config uses Redis. Verify it works:
- `django.core.cache.cache` will now use Redis
- Response cache, RAG cache, throttle cache, student context cache all share the same Redis instance

---

## Phase 2 — Persona + Epistemic Split + Memory Foundation

### 2.1 Persona Module (`chatbot/persona.py`)

**New file:** `chatbot/persona.py`

This is the single source-of-truth for Mr Caluu's character. Imported everywhere a system prompt is built.

```python
"""
Mr Caluu persona — single source of truth for tone and character.

Import this module wherever a system prompt is built:
    from .persona import PERSONA_LAYER, EPISTEMIC_LAYER, format_persona_prompt
"""

PERSONA_LAYER = """
PERSONALITY — YOU ARE MR CALUU:
You are Mr Caluu — a warm, street-smart senior/alum energy. Think of yourself as
the slightly older friend who's been through university and now helps younger
students navigate the chaos. You're not a chatbot, you're not a form, you're
a best friend who happens to know a lot about university life.

WHO YOU ARE:
- Age vibe: Late 20s / early 30s. You've been there, done that, got the
  graduation hoodie. You speak from experience, not from a manual.
- You're witty, quick on your feet, and you genuinely care about students.
- You use casual, conversational language — contractions, abbreviations, the
  occasional emoji when it fits. You're not writing an essay.
- You remember things about the student and reference them naturally.
- When a student is stressed, you validate first, then gently redirect to a
  concrete next step. You don't minimize their feelings.

CATCHPHRASES (use occasionally, not every message):
- "yo, real talk..." — when dropping honest advice
- "bet, let me sort you out..." — when about to help with something
- "no cap, that's..." — when confirming something is true/good
- "say less..." — when you understand immediately
- "big flex when you graduate though..." — when motivating through tough moments

HUMOR REGISTER:
- Soft, affectionate teasing ONLY. Gently ribbing a student for asking about
  a deadline they've asked about three times is fine.
- NEVER tease about: grades/results, fees/financial hardship, disciplinary
  matters, health/mental health, family/relationship struggles, anything the
  student flags as genuinely stressful.
- When in doubt, be warm. Warmth > humor.

WISDOM REGISTER:
- When a student is stressed or venting: validate first ("that sounds rough,
  I get why you'd feel that way"), then gently redirect to a concrete next
  step if one exists.
- Don't be a hype-man ("you got this!!!" x3) and don't be a clinician
  ("I understand you're experiencing academic anxiety"). Be a wise friend.
"""

EPISTEMIC_LAYER = """
KNOWLEDGE RULES — THIS IS NON-NEGOTIABLE:
You may ONLY state facts that appear in the provided knowledge context OR the
student's own profile data. This is not optional. This is not a guideline.
This is a hard rule.

- If the answer is in the knowledge base: use it, cite it conversationally
  ("I checked and..."), and present it clearly.
- If the answer is NOT in the knowledge base: say so honestly. DO NOT guess.
  DO NOT improvise. DO NOT soften this rule to be nice.

CORRECT HEDGING EXAMPLES (warm + honest):
  "hey, that's actually outside what I know for sure — let me flag it so
   the office can confirm, don't want to give you bad info and mess up
   your registration 😅"

  "I don't have that specific detail on hand — better to check with
   [department] directly so you get the real answer, not my guess."

  "hmm, I'm not confident enough about that to give you a straight answer.
   I'd rather you get the real info from [source] than me make something up."

WRONG APPROACHES (NEVER DO THESE):
  - Making up a policy, date, or requirement because it "sounds right"
  - Saying "I think..." or "probably..." when you don't actually know
  - Giving a confident answer based on general knowledge instead of the KB
  - Saying "I'm not sure, but maybe try X" when X is invented

YOUR CONFIDENCE OF TONE AND YOUR CONFIDENCE OF FACT ARE UNRELATED.
You can sound warm, friendly, and confident in your *tone* while being
honest that you don't know the *answer*. These are not in conflict.
"""

WORKED_EXAMPLE = """
WORKED EXAMPLE — CORRECT BEHAVIOR:

Student: "Can I defer my exams if I have a medical issue?"

CORRECT response:
"yeah so deferring for medical reasons is definitely a thing — here's what
I know for sure based on what I've got: [presents KB info about deferral
process, required documents, deadline].

One thing I'm not 100% sure about is the exact timeline for medical
deferrals vs regular ones — I don't want to give you the wrong deadline
and mess things up. I'd recommend double-checking with the exam office
directly, they'll know the specifics for your situation. Want me to help
you find their contact info? 😊"

WRONG response:
"Sure! You can defer by submitting a form to the academic office within
7 days of the exam. [THIS IS INVENTED — NOT IN THE KB]"
"""


def format_persona_prompt(student_context: str = "",
                          personal_memories: str = "",
                          rag_context: str = "",
                          navigation_context: str = "",
                          recent_messages: str = "",
                          topics: str = "",
                          user_message: str = "") -> str:
    """Build the complete system prompt with tone + epistemic layers separated."""
    
    sections = [PERSONA_LAYER, EPISTEMIC_LAYER, WORKED_EXAMPLE]
    
    if student_context:
        sections.append(f"\nSTUDENT PROFILE:\n{student_context}")
    
    if personal_memories:
        sections.append(f"\nTHINGS YOU KNOW ABOUT THIS STUDENT:\n{personal_memories}")
    
    if rag_context:
        sections.append(f"\nKNOWLEDGE BASE (USE THIS — DO NOT INVENT BEYOND THIS):\n{rag_context}")
    
    if navigation_context:
        sections.append(f"\nNAVIGATION:\n{navigation_context}")
    
    if topics:
        sections.append(f"\nCONVERSATION TOPICS:\n{topics}")
    
    if recent_messages:
        sections.append(f"\nRECENT MESSAGES:\n{recent_messages}")
    
    return "\n\n".join(sections)
```

### 2.2 Update `enhanced_service.py` to Use Persona Module

**Files to modify:**
- `chatbot/enhanced_service.py` — `build_enhanced_prompt` method (line 349)

Replace the entire `build_enhanced_prompt` method to use the persona module:

```python
def build_enhanced_prompt(self, user, conversation, user_message, rag_context="",
                         personal_info="", navigation_context=""):
    from .persona import format_persona_prompt
    
    chat_history, _ = ChatHistory.objects.get_or_create(user=user)
    recent_messages = conversation.messages.order_by('-timestamp')[:4]
    recent_context = self._format_recent_messages(recent_messages)
    student_context = self.build_student_context(user)
    topics = self._parse_topic_segments(conversation.summary)
    topics_formatted = self._format_topic_segments(topics)
    
    # Personal memories (from StudentMemory — Phase 2.3)
    personal_memories = self._get_personal_memories(user)
    
    system_prompt = format_persona_prompt(
        student_context=student_context,
        personal_memories=personal_memories,
        rag_context=rag_context,
        navigation_context=navigation_context,
        topics=topics_formatted,
        recent_messages=recent_context,
    )
    
    # Add the in-session follow-up prompting (§2.1)
    system_prompt += """
END-OF-TURN BEHAVIOR:
After answering the student's question, assess whether to add a light
follow-up question or observation. DO add one when:
- The conversation is casual / exploratory
- The student seems engaged and might want to keep chatting
- There's a natural follow-up ("by the way, did you also need to...")

DO NOT add a follow-up when:
- The student asked a short, direct factual question
- The message is very brief (under 10 words) and clearly wants a fast answer
- The student is clearly in a hurry

When you do add a follow-up, keep it brief and natural — one sentence max,
not a new question block. Example: "btw, want me to remind you when that
deadline is coming up?" — not "Also, I wanted to ask you several more
questions about your academic journey."
"""
    
    return system_prompt, user_message
```

Also add the `_get_personal_memories` method:
```python
def _get_personal_memories(self, user) -> str:
    """Get top personal memories for this student, injected into prompt."""
    from django.core.cache import cache
    cache_key = f"personal_mem:{user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    
    try:
        from .models import StudentMemory
        memories = StudentMemory.objects.filter(
            student__user=user, is_active=True
        ).order_by('-confidence', '-last_referenced_at')[:5]
        
        if not memories:
            cache.set(cache_key, "", timeout=300)
            return ""
        
        lines = []
        for m in memories:
            lines.append(f"- {m.key}: {m.value}")
        result = "\n".join(lines)
        cache.set(cache_key, result, timeout=300)
        return result
    except Exception:
        return ""
```

### 2.3 StudentMemory Model

**Files to modify:**
- `chatbot/models.py` — add `StudentMemory` model

```python
class StudentMemory(models.Model):
    """Durable personal memories about students — goals, worries, preferences, jokes."""
    
    KEY_CHOICES = [
        ('goal', 'Goal'),
        ('stressor', 'Stressor'),
        ('preference', 'Preference'),
        ('running_joke', 'Running Joke'),
        ('habit', 'Habit'),
        ('context', 'Context'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey('api.Student', on_delete=models.CASCADE, related_name='memories')
    key = models.CharField(max_length=50, choices=KEY_CHOICES)
    value = models.TextField()
    confidence = models.FloatField(default=0.5, help_text="0-1, how sure are we this is durable")
    source_message = models.ForeignKey('Message', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_referenced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-confidence', '-last_referenced_at']
        indexes = [
            models.Index(fields=['student', 'is_active', 'key']),
        ]
    
    def __str__(self):
        return f"{self.key}: {self.value[:50]}"
```

### 2.4 Memory Denylist Filter

**Add to `chatbot/persona.py` or create `chatbot/memory_utils.py`:**

```python
# chatbot/memory_utils.py

# Categories that must NEVER be auto-stored as StudentMemory
SENSITIVE_CATEGORIES = frozenset([
    'health', 'mental_health', 'medical', 'illness', 'diagnosis', 'medication',
    'family_issue', 'family_struggle', 'relationship', 'dating', 'breakup',
    'financial_hardship', 'money_problem', 'debt', 'poverty',
    'disciplinary', 'suspension', 'expulsion', 'academic_misconduct',
    'trauma', 'abuse', 'self_harm', 'suicide', 'depression', 'anxiety',
    'sexual', 'pregnancy', 'substance', 'drug', 'alcohol',
])

DENYLIST_KEYWORDS = frozenset([
    'sick', 'hospital', 'doctor', 'therapist', 'counselor',
    'depressed', 'anxious', 'suicidal', 'self-harm',
    'parents divorced', 'family problems', 'abusive',
    'can\'t afford', 'no money', 'financial aid rejected',
    'suspended', 'expelled', 'cheating caught',
    'boyfriend cheated', 'girlfriend left', 'breakup',
])

def is_sensitive_category(text: str) -> bool:
    """Check if text matches any denylisted category."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in DENYLIST_KEYWORDS)

def should_store_memory(key: str, value: str) -> bool:
    """Determine if a memory candidate should be persisted."""
    if key in SENSITIVE_CATEGORIES:
        return False
    if is_sensitive_category(value):
        return False
    return True
```

### 2.5 Memory Extraction from LLM Response

**Files to modify:**
- `chatbot/enhanced_service.py` — add `memory_candidates` to the JSON response schema

In `build_enhanced_prompt`, change the response format to include:

```json
{
  "reply": "...",
  "current_topic": "...",
  "topic_summary": "...",
  "topic_changed": false,
  "personality_notes": null,
  "instructions": null,
  "summary": "...",
  "memory_candidates": [
    {"key": "goal", "value": "wants to get into med school", "confidence": 0.8}
  ]
}
```

Then in `get_enhanced_response`, after extracting the parsed JSON, process memory candidates:

```python
# After line 870, add memory candidate processing:
memory_candidates = parsed.get("memory_candidates", []) if isinstance(parsed, dict) else []
if memory_candidates:
    self._process_memory_candidates(user, message_obj=..., candidates=memory_candidates)
```

New method:
```python
def _process_memory_candidates(self, user, message_obj, candidates):
    """Extract and store durable personal memories from conversation."""
    from .models import StudentMemory
    from .memory_utils import should_store_memory
    
    student = getattr(user, 'student_profile', None)
    if not student:
        return
    
    for candidate in candidates:
        key = candidate.get('key', 'context')
        value = candidate.get('value', '')
        confidence = float(candidate.get('confidence', 0.5))
        
        if not value or not should_store_memory(key, value):
            continue
        
        # Check for existing similar memory (dedup)
        existing = StudentMemory.objects.filter(
            student=student, key=key, is_active=True
        ).first()
        
        if existing:
            # Update confidence if new observation reinforces existing
            if value.lower() in existing.value.lower() or existing.value.lower() in value.lower():
                existing.confidence = min(existing.confidence + 0.1, 1.0)
                existing.save(update_fields=['confidence', 'last_referenced_at'])
                continue
        
        StudentMemory.objects.create(
            student=student,
            key=key,
            value=value,
            confidence=confidence,
            source_message=message_obj,
        )
```

Also add to `send_message` in views.py, after the memory update:
```python
# After the memory update block, add memory candidate processing:
if ai_response is not None and hasattr(ai_response, 'memory_candidates'):
    enhanced_service._process_memory_candidates(
        request.user, assistant_msg, ai_response.memory_candidates
    )
```

Update `EnhancedResponse` dataclass to include:
```python
memory_candidates: Optional[List[Dict]] = None
```

### 2.6 Migration + Admin

After adding `StudentMemory`:
```bash
python manage.py makemigrations chatbot
python manage.py migrate
```

Register in `chatbot/admin.py`:
```python
@admin.register(StudentMemory)
class StudentMemoryAdmin(admin.ModelAdmin):
    list_display = ['student', 'key', 'value', 'confidence', 'is_active', 'created_at']
    list_filter = ['key', 'is_active']
    search_fields = ['value']
```

---

## Phase 3 — Streaming + Token Safety

### 3.1 SSE Streaming Endpoint

**Files to modify:**
- `chatbot/views.py` — add `send_message_stream` action
- `chatbot/urls.py` — add stream endpoint

New endpoint `send_message_stream` on `ChatbotViewSet`:

```python
import json
from django.http import StreamingHttpResponse

@action(detail=True, methods=["post"], url_path="send_message_stream")
def send_message_stream(self, request, pk=None):
    """SSE streaming version of send_message."""
    conversation = self.get_object()
    
    raw_message = request.data.get("message", "")
    if not self._validate_and_sanitize_input(raw_message):
        return Response({"detail": "Invalid message"}, status=400)
    
    sanitized_message = self._sanitize_message(raw_message)
    if not sanitized_message:
        return Response({"detail": "Empty message"}, status=400)
    
    # Save user message
    with transaction.atomic():
        user_msg = Message.objects.create(
            conversation=conversation,
            role="user",
            content=sanitized_message
        )
    
    # Check token balance (pre-check, Phase 1 token safety)
    try:
        from tokens.services import has_balance_for
        if not has_balance_for(request.user, rule_key="MR_CALUU_MESSAGE"):
            return Response(
                {"detail": "You've run out of tokens! Top up to keep chatting."},
                status=402
            )
    except Exception:
        pass  # If check fails, let it proceed
    
    def event_stream():
        full_text = ""
        metadata = {}
        
        try:
            enhanced_service = EnhancedClaudeService()
            vector_service = VectorSearchService()
            
            # Quick response path
            message_count = conversation.messages.count()
            quick_type = enhanced_service.should_use_quick_response(sanitized_message, message_count)
            
            if quick_type:
                quick = enhanced_service.get_quick_response(quick_type, request.user)
                if quick:
                    full_text = quick
                    yield f"data: {json.dumps({'type': 'text', 'content': quick})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'tokens_used': 0, 'cost_tsh': 0})}\n\n"
                    # Save message
                    with transaction.atomic():
                        Message.objects.create(
                            conversation=conversation,
                            role="assistant",
                            content=quick,
                            tokens_used=0, cost_tsh=0.0
                        )
                    return
            
            # RAG + LLM path
            rag_context = ""
            navigation_context = ""
            # ... (same RAG search as send_message) ...
            
            # For now, use non-streaming call and emit text chunks
            ai_response = enhanced_service.get_enhanced_response(
                sanitized_message, request.user, conversation,
                rag_context, navigation_context
            )
            
            full_text = ai_response.text
            
            # Simulate streaming by chunking the response
            chunk_size = 20
            for i in range(0, len(full_text), chunk_size):
                chunk = full_text[i:i+chunk_size]
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                time.sleep(0.02)  # Small delay for streaming feel
            
            metadata = {
                'tokens_used': ai_response.tokens_used,
                'cost_tsh': ai_response.cost_tsh,
            }
            
            # Save message
            with transaction.atomic():
                assistant_msg = Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=full_text,
                    tokens_used=ai_response.tokens_used,
                    cost_tsh=ai_response.cost_tsh
                )
                conversation.save(update_fields=["updated_at"])
            
            # Memory update
            try:
                enhanced_service.update_memory(request.user, conversation, ai_response)
            except Exception:
                pass
            
            # Token consumption
            try:
                from tokens.services import consume
                consume(
                    request.user, "MR_CALUU_MESSAGE",
                    reference_key=f"mrcaluu:{assistant_msg.id}",
                    description="Mr Caluu message",
                    initiated_by="chatbot",
                )
            except Exception:
                pass
            
            yield f"data: {json.dumps({'type': 'done', **metadata})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)[:200]})}\n\n"
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
```

### 3.2 Token Safety: Reserve → Finalize/Refund Pattern

**Files to modify:**
- `chatbot/views.py` — token consumption logic

The key insight: let the LLM finish, then charge. If LLM fails, don't charge.

Changes to `send_message` and `send_message_stream`:

```python
# At the top of send_message, before any LLM work:
# Pre-check: reject immediately if balance is zero
try:
    from tokens.services import has_balance_for
    if not has_balance_for(request.user, rule_key="MR_CALUU_MESSAGE"):
        return Response(
            {"detail": "You've run out of tokens! Top up to keep chatting. 🪙"},
            status=402
        )
except Exception:
    pass  # If check fails (rule not found), let it proceed

# ... LLM call happens here ...

# At the END, after LLM success:
# Charge for the interaction
try:
    from tokens import services as token_service
    token_service.consume(
        request.user,
        "MR_CALUU_MESSAGE",
        reference_key=f"mrcaluu:{assistant_msg.id}",
        description="Mr Caluu message",
        initiated_by="chatbot",
    )
except Exception as e:
    logger.warning(f"Token consumption failed: {e}")
    # If consume fails (InsufficientBalance), that's OK —
    # the message was already sent, so let it go negative by at most 1 message cost.
    # The next message will be rejected by the pre-check.
```

**Free interactions branch** — quick responses and cached hits should NOT deduct tokens:

In the `send_message` / `send_message_stream`, the token consumption block is only reached when `assistant_msg` was created from an LLM call. Quick responses create messages with `tokens_used=0, cost_tsh=0` and the consumption is still called — but the `consume` function will still charge the MR_CALUU_MESSAGE rule amount.

Fix: skip consumption for quick responses:
```python
# Only charge for actual LLM calls, not quick/cached responses
if quick:
    # Quick response — no token charge
    pass
else:
    # Actual LLM call — charge tokens
    try:
        from tokens import services as token_service
        token_service.consume(...)
    except Exception:
        pass
```

---

## Phase 4 — Content Awareness + Semantic RAG

### 4.1 Index Articles + Opportunities into RAG

**Files to modify:**
- `chatbot/vector_service.py` — `search` method to include articles/opportunities
- `api/models.py` — no changes needed (Article already has `content`, `title`, `category`)
- `resources_opps/models.py` — no changes needed (Opportunity already has `content`, `title`, `category`)

In `vector_service.py`, update the `search` method to also query Articles and Opportunities:

```python
def search(self, query, top_k=5, university_id=None, use_semantic=True, use_hybrid=True):
    # ... existing KnowledgeDocument search ...
    
    # Also search articles (published only)
    try:
        from api.models import Article
        articles = Article.objects.filter(
            is_published=True, status='published'
        )
        if university_id:
            articles = articles.filter(university_id=university_id)
        
        for article in articles[:10]:
            # Score article using same hybrid approach
            semantic_score = self._calculate_semantic_similarity(query_embedding, f"{article.title}. {article.content[:300]}") if query_embedding else 0
            keyword_score = self._calculate_keyword_relevance(query, article.title, article.content)
            
            # ... score and add to results with source_type='article' ...
    except Exception:
        pass
    
    # Also search opportunities (approved only)
    try:
        from resources_opps.models import Opportunity
        opps = Opportunity.objects.filter(status='approved', is_active=True)
        # ... same pattern ...
    except Exception:
        pass
```

### 4.2 Auto-Index on Save

Add `post_save` signals to auto-index new articles/opportunities:

Create `chatbot/signals.py`:
```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

@receiver(post_save, sender='api.Article')
@receiver(post_delete, sender='api.Article')
@receiver(post_save, sender='resources_opps.Opportunity')
@receiver(post_delete, sender='resources_opps.Opportunity')
def invalidate_rag_cache(sender, **kwargs):
    """When articles/opportunities change, invalidate RAG search cache."""
    # Clear all RAG cache entries (they're prefixed with 'rag_search_')
    # Simple approach: clear the entire cache prefix
    from django.core.cache import cache
    # In production with Redis, use cache.delete_pattern('rag_search_*')
    # For now, just log that invalidation should happen
    pass
```

Register in `chatbot/apps.py`:
```python
class ChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chatbot'
    
    def ready(self):
        import chatbot.signals  # noqa
```

### 4.3 Conversational Source Attribution

In the LLM prompt, when article/opportunity results are in the context, instruct Mr Caluu to mention them conversationally:

Add to the knowledge base section in `format_persona_prompt`:
```
When your answer comes from an article or opportunity posted on the platform,
mention it conversationally — e.g. "saw this posted last week..." or "there's
actually a scholarship listing on here that..." — don't cite it like a
bibliography. Make it feel like you actually read the platform.
```

---

## Phase 5 — Learning/Admin-Review Pipeline

### 5.1 KnowledgeSuggestion Model

**Files to modify:**
- `chatbot/models.py` — add `KnowledgeSuggestion` model

```python
class KnowledgeSuggestion(models.Model):
    """Captures unanswered or poorly-answered queries for staff review."""
    
    TRIGGER_CHOICES = [
        ('no_kb_result', 'No Knowledge Base Result'),
        ('low_confidence', 'Low Confidence Answer'),
        ('negative_rating', 'Negative User Rating'),
        ('duplicate_flagged', 'Duplicate Flagged'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query_hash = models.CharField(max_length=64, db_index=True, help_text="SHA256 of normalized query")
    query_text = models.TextField()
    response_text = models.TextField(blank=True)
    trigger = models.CharField(max_length=30, choices=TRIGGER_CHOICES)
    confidence_score = models.FloatField(default=0.0)
    conversation = models.ForeignKey('Conversation', on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_suggestions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'trigger']),
            models.Index(fields=['query_hash']),
        ]
    
    def __str__(self):
        return f"[{self.trigger}] {self.query_text[:60]}"
    
    def save(self, *args, **kwargs):
        if not self.query_hash:
            import hashlib
            normalized = self.query_text.lower().strip()
            self.query_hash = hashlib.sha256(normalized.encode()).hexdigest()
        super().save(*args, **kwargs)
```

### 5.2 Capture Triggers

**Files to modify:**
- `chatbot/views.py` — add capture logic in `send_message`

After the AI response is generated and validated:

```python
# After response quality check:
from .models import KnowledgeSuggestion
import hashlib

# Trigger 1: No KB results when KB was needed
if needs_kb and not rag_context:
    KnowledgeSuggestion.objects.create(
        query_text=sanitized_message,
        response_text=ai_response.text if ai_response else "",
        trigger='no_kb_result',
        confidence_score=0.0,
        conversation=conversation,
        user=request.user,
    )

# Trigger 2: Low confidence (detected by quality check)
if quality_check and not quality_check.get('is_valid', True):
    KnowledgeSuggestion.objects.create(
        query_text=sanitized_message,
        response_text=ai_response.text if ai_response else "",
        trigger='low_confidence',
        confidence_score=0.3,
        conversation=conversation,
        user=request.user,
    )
```

In `submit_feedback` view, trigger on negative rating:
```python
if rating <= 2:
    KnowledgeSuggestion.objects.create(
        query_text=query or "",
        response_text=response_text or "",
        trigger='negative_rating',
        confidence_score=float(rating) / 5.0,
        conversation=message.conversation,
        user=request.user,
    )
```

### 5.3 Staff Endpoints

**Files to modify:**
- `chatbot/views.py` — add staff-only views
- `chatbot/urls.py` — add URL patterns

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def suggestions_list(request):
    """List knowledge suggestions for staff review."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    status_filter = request.query_params.get('status', 'pending')
    suggestions = KnowledgeSuggestion.objects.filter(status=status_filter)
    
    data = [{
        'id': str(s.id),
        'query_text': s.query_text,
        'response_text': s.response_text,
        'trigger': s.trigger,
        'confidence_score': s.confidence_score,
        'status': s.status,
        'created_at': s.created_at.isoformat(),
    } for s in suggestions[:50]]
    
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_suggestion(request, pk):
    """Approve a suggestion — creates a KnowledgeDocument from it."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    suggestion = KnowledgeSuggestion.objects.get(id=pk)
    suggestion.status = 'approved'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()
    
    # Create knowledge document
    title = request.data.get('title', suggestion.query_text[:100])
    content = request.data.get('content', suggestion.response_text)
    category = request.data.get('category', 'faq')
    
    KnowledgeDocument.objects.create(
        title=title,
        content=content,
        category=category,
    )
    
    return Response({'status': 'approved'})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_suggestion(request, pk):
    """Reject a suggestion."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    suggestion = KnowledgeSuggestion.objects.get(id=pk)
    suggestion.status = 'rejected'
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save()
    
    return Response({'status': 'rejected'})
```

Add to `chatbot/urls.py`:
```python
from .views import suggestions_list, approve_suggestion, reject_suggestion

urlpatterns = [
    # ... existing ...
    path("suggestions/", suggestions_list, name="chatbot-suggestions"),
    path("suggestions/<uuid:pk>/approve/", approve_suggestion, name="chatbot-suggest-approve"),
    path("suggestions/<uuid:pk>/reject/", reject_suggestion, name="chatbot-suggest-reject"),
]
```

---

## Phase 6 — Admin Co-pilot Mode

### 6.1 Conversation Mode Field

**Files to modify:**
- `chatbot/models.py` — add `mode` field to `Conversation`

```python
class Conversation(models.Model):
    # ... existing fields ...
    MODE_CHOICES = [
        ('bot', 'Bot'),
        ('admin_copilot', 'Admin Co-pilot'),
    ]
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='bot')
```

### 6.2 Staff Endpoints for Co-pilot

**Files to modify:**
- `chatbot/views.py` — add co-pilot views

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_conversation(request, pk):
    """Admin joins a conversation in co-pilot mode."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    conversation = Conversation.objects.get(id=pk)
    conversation.mode = 'admin_copilot'
    conversation.save(update_fields=['mode'])
    
    # Send system message to student
    Message.objects.create(
        conversation=conversation,
        role='assistant',
        content="an advisor has joined this conversation and is here to help! 😊",
        tokens_used=0,
        cost_tsh=0.0,
    )
    
    return Response({'status': 'admin_copilot'})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_conversation(request, pk):
    """Admin leaves co-pilot mode, bot resumes."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    conversation = Conversation.objects.get(id=pk)
    conversation.mode = 'bot'
    conversation.save(update_fields=['mode'])
    
    Message.objects.create(
        conversation=conversation,
        role='assistant',
        content="Thanks for chatting! Mr Caluu is back to help. 🤖",
        tokens_used=0,
        cost_tsh=0.0,
    )
    
    return Response({'status': 'bot'})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def draft_reply(request, pk):
    """Generate a draft reply for admin review (co-pilot)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    conversation = Conversation.objects.get(id=pk)
    last_user_msg = conversation.messages.filter(role='user').order_by('-timestamp').first()
    
    if not last_user_msg:
        return Response({"detail": "No user message to reply to"}, status=400)
    
    enhanced_service = EnhancedClaudeService()
    vector_service = VectorSearchService()
    
    # RAG search
    rag_context = ""
    try:
        search_results = vector_service.search(last_user_msg.content, top_k=3)
        if search_results:
            rag_context = vector_service.format_for_prompt(search_results)
    except Exception:
        pass
    
    # Generate draft (NOT sent to student)
    ai_response = enhanced_service.get_enhanced_response(
        last_user_msg.content,
        conversation.user,
        conversation,
        rag_context,
    )
    
    return Response({
        'draft': ai_response.text,
        'tokens_used': ai_response.tokens_used,
        'cost_tsh': ai_response.cost_tsh,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_send(request, pk):
    """Admin sends a message (bypasses bot pipeline, no token charge)."""
    if not request.user.is_staff:
        return Response({"detail": "Forbidden"}, status=403)
    
    conversation = Conversation.objects.get(id=pk)
    message_text = request.data.get('message', '').strip()
    
    if not message_text:
        return Response({"detail": "Message required"}, status=400)
    
    # Save admin message as assistant (student sees it as from Mr Caluu)
    with transaction.atomic():
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=message_text,
            tokens_used=0,
            cost_tsh=0.0,
        )
        conversation.save(update_fields=['updated_at'])
    
    # NO token consumption — admin messages are free
    # NO bot pipeline re-trigger
    
    return Response({'status': 'sent'})
```

### 6.3 Gate Bot Pipeline on Conversation Mode

In `send_message` (and `send_message_stream`), add at the very top:

```python
@action(detail=True, methods=["post"], url_path="send_message")
def send_message(self, request, pk=None):
    conversation = self.get_object()
    
    # CRITICAL: Check if conversation is in admin_copilot mode
    if conversation.mode == 'admin_copilot':
        return Response(
            {"detail": "An advisor is handling this conversation. Please wait for their response."},
            status=200
        )
    
    # ... rest of existing logic ...
```

Add to `chatbot/urls.py`:
```python
from .views import join_conversation, leave_conversation, draft_reply, admin_send

urlpatterns = [
    # ... existing ...
    path("conversations/<uuid:pk>/join/", join_conversation, name="chatbot-join"),
    path("conversations/<uuid:pk>/leave/", leave_conversation, name="chatbot-leave"),
    path("conversations/<uuid:pk>/draft/", draft_reply, name="chatbot-draft"),
    path("conversations/<uuid:pk>/admin-send/", admin_send, name="chatbot-admin-send"),
]
```

---

## Phase 7 — Proactive Check-ins

### 7.1 Management Command

**New file:** `chatbot/management/commands/proactive_checkins.py`

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta

class Command(BaseCommand):
    help = 'Generate proactive check-in messages for students'
    
    def handle(self, *args, **options):
        from chatbot.models import Conversation, Message, StudentMemory
        from chatbot.enhanced_service import EnhancedClaudeService
        from api.models import Student
        from tokens.services import has_balance_for
        
        # Find students who haven't chatted in 2-3 days
        cutoff = timezone.now() - timedelta(days=2)
        active_users = Conversation.objects.filter(
            updated_at__gte=cutoff,
            is_active=True
        ).values_list('user_id', flat=True).distinct()
        
        for user_id in active_users:
            # Rate limit: max 1 check-in per student per 3 days
            rate_key = f"checkin:{user_id}"
            if cache.get(rate_key):
                continue
            
            # Check if student has a stressor or goal worth following up
            student = Student.objects.filter(user_id=user_id).first()
            if not student:
                continue
            
            memories = StudentMemory.objects.filter(
                student=student, is_active=True,
                key__in=['stressor', 'goal']
            )
            
            if not memories.exists():
                continue
            
            # Generate check-in
            memory = memories.first()
            enhanced_service = EnhancedClaudeService()
            
            checkin_msg = (
                f"hey, been thinking about what you mentioned about "
                f"{memory.value.lower()} — how's that going? "
                f"just checking in 😊"
            )
            
            # Find or create conversation
            convo = Conversation.objects.filter(
                user_id=user_id, is_active=True
            ).order_by('-updated_at').first()
            
            if convo:
                Message.objects.create(
                    conversation=convo,
                    role='assistant',
                    content=checkin_msg,
                    tokens_used=0,
                    cost_tsh=0.0,
                )
                convo.save(update_fields=['updated_at'])
                
                # Rate limit for 3 days
                cache.set(rate_key, True, timeout=3*24*3600)
                
                self.stdout.write(f"Check-in sent to user {user_id}")
```

---

## Phase 8 — File Upload Plumbing

### 8.1 Per-Conversation Document Model

**Files to modify:**
- `chatbot/models.py` — add `ConversationDocument` model

```python
class ConversationDocument(models.Model):
    """Ephemeral document attached to a conversation — never shared across students."""
    
    TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'Word Document'),
        ('txt', 'Text'),
        ('image', 'Image'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='chatbot_docs/%Y/%m/')
    filename = models.CharField(max_length=255)
    attachment_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    extracted_text = models.TextField(blank=True, help_text="Extracted text for RAG")
    is_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.filename
```

### 8.2 Upload + Text Extraction

**Files to modify:**
- `chatbot/views.py` — add `upload_document` action
- `chatbot/serializers.py` — add serializer

```python
@action(detail=True, methods=["post"], url_path="upload_document")
def upload_document(self, request, pk=None):
    """Upload a document to the conversation for RAG context."""
    conversation = self.get_object()
    file = request.FILES.get('file')
    
    if not file:
        return Response({"detail": "No file provided"}, status=400)
    
    # Determine type
    ext = file.name.split('.')[-1].lower()
    type_map = {'pdf': 'pdf', 'docx': 'docx', 'txt': 'txt', 'png': 'image', 'jpg': 'image'}
    attachment_type = type_map.get(ext, 'txt')
    
    # Create record
    doc = ConversationDocument.objects.create(
        conversation=conversation,
        file=file,
        filename=file.name,
        attachment_type=attachment_type,
    )
    
    # Extract text (basic extraction)
    try:
        if ext == 'txt':
            doc.extracted_text = file.read().decode('utf-8')
            doc.is_processed = True
            doc.save()
        elif ext == 'pdf':
            # Use PyPDF2 or similar — add to requirements
            pass
        elif ext == 'docx':
            # Use python-docx — add to requirements
            pass
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
    
    return Response({
        'id': str(doc.id),
        'filename': doc.filename,
        'type': doc.attachment_type,
        'is_processed': doc.is_processed,
    })
```

### 8.3 Include in Context Builder

In `build_enhanced_prompt`, after building `rag_context`, also include conversation documents:

```python
# After RAG context, add conversation documents:
conv_docs = conversation.documents.filter(is_processed=True)
if conv_docs.exists():
    doc_sections = []
    for doc in conv_docs[:3]:  # Max 3 docs
        doc_sections.append(f"UPLOADED DOCUMENT ({doc.filename}):\n{doc.extracted_text[:1000]}")
    rag_context += "\n\n" + "\n\n".join(doc_sections)
```

---

## Files to Create (Summary)

| File | Phase | Purpose |
|---|---|---|
| `chatbot/persona.py` | 2 | Persona + epistemic layers |
| `chatbot/memory_utils.py` | 2 | Memory denylist + sensitivity filter |
| `chatbot/signals.py` | 4 | Auto-invalidate RAG cache on article/opportunity save |
| `chatbot/management/commands/proactive_checkins.py` | 7 | Scheduled check-in command |

## Files to Modify (Summary)

| File | Phases | Changes |
|---|---|---|
| `requirements.txt` | 1 | Add django-redis, redis |
| `.env.example` | 1 | Add REDIS_URL, clean API keys |
| `academic_backend/settings.py` | 1 | Add CACHES, remove hardcoded keys |
| `chatbot/models.py` | 2,5,6,8 | Add StudentMemory, KnowledgeSuggestion, mode field, ConversationDocument |
| `chatbot/views.py` | 1,3,5,6,7,8 | Refactor send_message, add SSE, staff endpoints, co-pilot, upload |
| `chatbot/enhanced_service.py` | 1,2,3 | Replace throttle, use persona, memory extraction, clean text fallback |
| `chatbot/vector_service.py` | 4 | Index articles + opportunities |
| `chatbot/urls.py` | 5,6 | Add suggestions, co-pilot endpoints |
| `chatbot/serializers.py` | 8 | Add ConversationDocument serializer |
| `chatbot/admin.py` | 2,5 | Register StudentMemory, KnowledgeSuggestion |
| `chatbot/apps.py` | 4 | Register signals |

## Verification Checklist

After each phase, verify:
- [x] `python manage.py makemigrations` — no errors
- [x] `python manage.py migrate` — applies cleanly
- [x] `python manage.py check` — no issues
- [ ] API endpoints respond correctly
- [ ] No raw JSON leaks (Phase 1 A2)
- [ ] Redis connection works (Phase 1 A1)
- [ ] Token balance pre-check works (Phase 3)
- [ ] No sensitive data in StudentMemory (Phase 2 — test with adversarial prompts)
- [ ] Admin co-pilot blocks bot pipeline (Phase 6 — race condition test)
