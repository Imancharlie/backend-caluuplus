from __future__ import annotations

import json
import re
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
import logging

from anthropic import Anthropic

# Gemini (Google) is the preferred AI provider for Mr. Caluu. The SDK is only
# required when a Gemini API key is configured, so the Anthropic fallback keeps
# working even if google-genai is not installed.
try:
    from google.genai import Client as GeminiClient
    from google.genai import types as gemini_types
except Exception:  # pragma: no cover - optional dependency
    GeminiClient = None
    gemini_types = None

logger = logging.getLogger(__name__)

from .models import ChatHistory, KnowledgeDocument
from api.models import Student, StudentCourse, TimetableSlot, Notification


@dataclass
class EnhancedResponse:
    text: str
    tokens_used: int
    input_tokens: int
    output_tokens: int
    cost_tsh: float
    summary: str
    personality_notes: Optional[str]
    instructions: Optional[str]
    current_topic: Optional[str] = None
    topic_changed: bool = False
    topic_summary: Optional[str] = None
    memory_candidates: Optional[List[Dict]] = None


class EnhancedClaudeService:
    """Enhanced Claude service with hierarchical memory and topic tracking"""
    
    def __init__(self) -> None:
        # Rate limiting (shared by both providers): Track last request time to
        # prevent API rate limits. Free tier: 5 req/min = 12s interval, Paid:
        # 50 req/min = 1.2s interval.
        self._last_request_time = None
        self._min_request_interval = float(getattr(settings, 'ANTHROPIC_MIN_REQUEST_INTERVAL', 12))

        # Choose the AI provider. Gemini is preferred when a key is configured;
        # otherwise we fall back to Anthropic Claude.
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or os.getenv('GEMINI_API_KEY', '')

        self._provider = 'anthropic'
        self._model = "claude-3-haiku-20240307"
        self._client = None
        self._gemini_client = None

        # Gemini path: if a Gemini key is configured (and the SDK is installed),
        # use Gemini and skip Anthropic entirely — no Anthropic key required.
        if gemini_key and GeminiClient is not None:
            try:
                self._gemini_client = GeminiClient(
                    api_key=gemini_key,
                    http_options=gemini_types.HttpOptions(timeout=45000),
                )
                self._provider = 'gemini'
                self._model = getattr(settings, 'GEMINI_MODEL', 'gemini-flash-latest')
                logger.info(
                    f"EnhancedClaudeService initialized (provider={self._provider}, "
                    f"model={self._model}) with {self._min_request_interval}s request interval"
                )
                return
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}. Falling back to Anthropic.")

        # Anthropic path: only reached when Gemini is unavailable or its init failed.
        # Try multiple ways to get the Anthropic API key
        api_key = None
        # Method 1: Check Django settings
        if hasattr(settings, 'ANTHROPIC_API_KEY'):
            api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        # Method 2: Check environment variable
        if not api_key:
            api_key = os.getenv('ANTHROPIC_API_KEY')
        # Method 3: Check settings with different case
        if not api_key and hasattr(settings, 'anthropic_api_key'):
            api_key = getattr(settings, 'anthropic_api_key', None)
        if not api_key:
            raise RuntimeError(
                "No AI provider configured. Set GEMINI_API_KEY (preferred) or "
                "ANTHROPIC_API_KEY in Django settings or as an environment variable."
            )
        self._client = Anthropic(api_key=api_key)

        logger.info(
            f"EnhancedClaudeService initialized (provider={self._provider}, "
            f"model={self._model}) with {self._min_request_interval}s request interval"
        )

    def _call_llm(self, system_prompt: str, user_content: str, max_tokens: int, timeout_seconds: int):
        """Dispatch a chat completion to the active provider (Gemini or Anthropic).

        Returns an object with ``.content`` (a list of ``{type, text}`` blocks)
        and ``.usage`` (``input_tokens`` / ``output_tokens``) so the rest of the
        pipeline is provider-agnostic.
        """
        if self._provider == 'gemini' and self._gemini_client is not None:
            resp = self._gemini_client.models.generate_content(
                model=self._model,
                contents=user_content,
                config=gemini_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                    temperature=0.2,
                    response_modalities=["TEXT"],
                ),
            )

            class _Usage:
                def __init__(self, p, o):
                    self.input_tokens = int(p)
                    self.output_tokens = int(o)

            try:
                text = (resp.text or "").strip()
            except Exception:
                text = ""
            usage_meta = getattr(resp, "usage_metadata", None)
            try:
                input_tokens = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                output_tokens = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
            except Exception:
                input_tokens = 0
                output_tokens = 0

            class _Block:
                def __init__(self, t):
                    self.type = "text"
                    self.text = t

            class _Resp:
                pass

            unified = _Resp()
            unified.content = [_Block(text)] if text else []
            unified.usage = _Usage(input_tokens, output_tokens)
            return unified

        # Default: Anthropic Claude
        return self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            timeout=timeout_seconds,
        )

    def _call_llm_streaming(self, system_prompt: str, user_content: str, max_tokens: int, timeout_seconds: int):
        """Yield text chunks as they are generated (native streaming).

        Yields strings of text. Caller consumes them in a generator loop.
        """
        if self._provider == 'gemini' and self._gemini_client is not None:
            for chunk in self._gemini_client.models.generate_content_stream(
                model=self._model,
                contents=user_content,
                config=gemini_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                    temperature=0.2,
                    response_modalities=["TEXT"],
                ),
            ):
                text = getattr(chunk, "text", None) or ""
                if text:
                    yield text
            return

        # Anthropic streaming
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            timeout=timeout_seconds,
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text

    def build_student_context(self, user) -> str:
        """Build comprehensive student context from existing models (Redis-cached)."""
        from django.core.cache import cache
        cache_key = f"student_ctx:{user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        lines: List[str] = []
        student: Student | None = getattr(user, "student_profile", None)
        if student:
            lines.append(f"Student: {user.display_name} | Email: {user.email}")
            lines.append(
                f"Programme: {student.program.name} ({student.program.duration} years) | College: {student.college.name} | University: {student.university.name}"
            )
            lines.append(f"Academic Level: Year {student.year}, Semester {student.semester}")
            
            # Program details
            try:
                program = student.program
                lines.append(f"Program Duration: {program.duration} years")
                
                # Get program courses structure if available
                from api.models import Course
                program_courses = Course.objects.filter(program=program).order_by('year', 'semester')
                if program_courses.exists():
                    total_credits = sum(c.credits for c in program_courses)
                    lines.append(f"Program Structure: {program_courses.count()} courses, {total_credits} total credits")
                    
                    # Show courses for current year/semester
                    current_courses = program_courses.filter(year=student.year, semester=student.semester)
                    if current_courses.exists():
                        lines.append(f"Expected Courses This Semester: {', '.join([f'{c.code} ({c.credits}cr)' for c in current_courses[:5]])}")
            except Exception as e:
                logger.debug(f"Error getting program details: {e}")

            # Current enrolled courses
            try:
                student_courses: StudentCourse | None = getattr(student, "student_courses", None)
                if student_courses and student_courses.courses:
                    compact = []
                    for _key, items in student_courses.get_periods().items():
                        for c in items:
                            code = c.get("code") or c.get("course_code") or "?"
                            name = c.get("name") or c.get("course_name") or "Course"
                            credits = c.get("credits", "")
                            if credits:
                                compact.append(f"{code} ({credits}cr)")
                            else:
                                compact.append(code)
                    lines.append(f"Enrolled Courses ({len(compact)}): {', '.join(compact[:8])}")
            except Exception:
                pass

            # Today's schedule
            today = timezone.now().strftime("%A").lower()
            today_classes = TimetableSlot.objects.filter(student=student, day_of_week=today).order_by("time_slot")
            if today_classes.exists():
                lines.append("Today's Schedule:")
                for t in today_classes:
                    lines.append(f" - {t.course_code or t.course_name or t.course} at {t.time_slot} in {t.venue}" + 
                               (f" (Instructor: {t.instructor})" if t.instructor else ""))
            else:
                lines.append("Today: No classes scheduled")

        unread = Notification.objects.filter(user=user, is_read=False).count()
        if unread:
            lines.append(f"Unread notifications: {unread}")
        result = "\n".join(lines)
        cache.set(cache_key, result, timeout=300)  # 5 min TTL
        return result

    def _format_recent_messages(self, messages) -> str:
        """Format last few messages for context - optimized to reduce tokens"""
        if not messages:
            return "New chat"
        
        formatted = []
        for msg in reversed(messages):
            role = "U" if msg.role == "user" else "C"  # Shortened for token efficiency
            # Limit to 80 chars instead of 100 for better token efficiency
            formatted.append(f"{role}: {msg.content[:80]}...")
        
        return "\n".join(formatted)

    def _parse_topic_segments(self, summary_json: str) -> List[Dict]:
        """Parse topic segments from JSON summary"""
        try:
            data = json.loads(summary_json or "{}")
            topics = data.get("topics", [])
            return topics if isinstance(topics, list) else []
        except Exception:
            return []

    def _format_topic_segments(self, topics: List[Dict]) -> str:
        """Format topic segments for prompt - optimized for tokens"""
        if not topics:
            return "None"
        # Only show last 2 topics instead of 3, and truncate summaries
        lines: List[str] = []
        for t in topics[-2:]:
            topic = t.get('topic', 'Gen')
            summary = t.get('summary', '')[:60]  # Limit summary to 60 chars
            lines.append(f"{topic}: {summary}")
        return " | ".join(lines)  # Use pipe separator instead of newlines

    def classify_query_intent(self, query: str) -> Dict[str, Any]:
        """Classify query intent and determine routing strategy"""
        query_lower = query.lower().strip()
        
        intent_patterns = {
            'procedure': [
                'how to', 'how do i', 'steps to', 'process to', 'procedure for',
                'postpone', 'defer', 'withdraw', 'register', 'enroll', 'drop',
                'apply for', 'submit', 'request', 'appeal'
            ],
            'regulation': [
                'regulation', 'rule', 'policy', 'requirement', 'guideline',
                'allowed', 'permitted', 'prohibited', 'forbidden', 'must', 'should',
                'academic integrity', 'plagiarism', 'cheating'
            ],
            'calendar': [
                'when is', 'date', 'deadline', 'holiday', 'break', 'exam period',
                'registration period', 'semester starts', 'semester ends',
                'academic calendar', 'event'
            ],
            'navigation': [
                'where is', 'how to find', 'navigate to', 'go to', 'access',
                'find', 'locate', 'show me', 'where can i'
            ],
            'faq': [
                'what is', 'what are', 'can i', 'do i need', 'should i',
                'is it possible', 'is there', 'does', 'explain'
            ],
            'academic_advice': [
                'advice', 'help with', 'struggling', 'difficulty', 'recommendation',
                'suggestion', 'tips', 'how to study', 'how to improve'
            ],
            'program_info': [
                'program', 'degree', 'major', 'curriculum', 'requirements',
                'prerequisites', 'courses in', 'what courses'
            ],
            'schedule': [
                'schedule', 'timetable', 'class', 'when is class', 'today',
                'tomorrow', 'next class'
            ]
        }
        
        detected_intents = []
        confidence_scores = {}
        
        for intent, patterns in intent_patterns.items():
            score = 0
            for pattern in patterns:
                if pattern in query_lower:
                    score += 1
            if score > 0:
                detected_intents.append(intent)
                confidence_scores[intent] = score
        
        # Determine primary intent
        primary_intent = max(confidence_scores.items(), key=lambda x: x[1])[0] if confidence_scores else 'faq'
        
        # Determine if it's a critical question (needs knowledge base)
        critical_keywords = ['regulation', 'rule', 'policy', 'procedure', 'how to', 'requirement']
        is_critical = any(kw in query_lower for kw in critical_keywords)
        
        return {
            'primary_intent': primary_intent,
            'all_intents': detected_intents,
            'confidence': confidence_scores,
            'is_critical': is_critical,
            'needs_knowledge_base': is_critical or primary_intent in ['procedure', 'regulation', 'faq']
        }
    
    def _extract_personal_info_from_message(self, message: str) -> str:
        """Extract personal information from user message"""
        personal_keywords = [
            "girlfriend", "boyfriend", "wife", "husband", "partner", "spouse",
            "family", "mother", "father", "mom", "dad", "sister", "brother", "sibling",
            "friend", "friends", "relationship", "dating", "married", "single",
            "hobby", "hobbies", "like", "love", "enjoy", "prefer", "favorite",
            "live", "living", "from", "born", "grew up", "studying", "work", "job"
        ]
        
        message_lower = message.lower()
        found_info = []
        
        for keyword in personal_keywords:
            if keyword in message_lower:
                # Extract context around the keyword
                start = max(0, message_lower.find(keyword) - 20)
                end = min(len(message), message_lower.find(keyword) + len(keyword) + 20)
                context = message[start:end].strip()
                if context not in found_info:
                    found_info.append(context)
        
        return " | ".join(found_info) if found_info else ""

    def build_enhanced_prompt(self, user, conversation, user_message: str, rag_context: str = "", 
                             personal_info: str = "", navigation_context: str = "") -> Tuple[str, str]:
        """Build comprehensive prompt using the persona module (tone + epistemic layers)."""

        # Get or create ChatHistory
        chat_history, _ = ChatHistory.objects.get_or_create(user=user)

        # Get last 2 message pairs for immediate context
        recent_messages = conversation.messages.order_by('-timestamp')[:4]
        recent_context = self._format_recent_messages(recent_messages)

        # Build student context (Redis-cached)
        student_context = self.build_student_context(user)

        # Personal memories (StudentMemory — Redis-cached)
        personal_memories = self._get_personal_memories(user)

        # Topics from hierarchical summary
        topics = self._parse_topic_segments(conversation.summary)
        topics_formatted = self._format_topic_segments(topics)

        # Phase 8: include per-conversation uploaded documents (ephemeral, student-only)
        try:
            conv_docs = conversation.documents.filter(is_processed=True)
            if conv_docs.exists():
                doc_sections = []
                for doc in conv_docs[:3]:
                    doc_sections.append(
                        f"UPLOADED DOCUMENT ({doc.filename}):\n{doc.extracted_text[:1200]}"
                    )
                if doc_sections:
                    rag_context = (rag_context + "\n\n" + "\n\n".join(doc_sections)).strip()
        except Exception:
            pass

        from .persona import format_persona_prompt
        system_prompt = format_persona_prompt(
            student_context=student_context,
            personal_memories=personal_memories,
            rag_context=rag_context,
            navigation_context=navigation_context,
            recent_messages=recent_context,
            topics=topics_formatted,
            user_message=user_message,
        )

        # Add grounding / KB instructions
        if rag_context:
            system_prompt += f"""
STUDENT'S QUESTION: "{user_message}"

YOUR TASK: Answer the question above using the knowledge base information provided. Extract and present the relevant information from the knowledge base directly. Do not give generic responses.

IMPORTANT: Reply with ONLY your conversational answer. No JSON, no metadata, no labels. Just the natural reply text."""
        else:
            system_prompt += f"""
STUDENT'S QUESTION: "{user_message}"

YOUR TASK: Respond helpfully, accurately, and specifically. If the answer is
NOT in the knowledge base or the student's profile, follow the epistemic rules
above — say what you don't know, and offer to escalate or note the gap.

IMPORTANT: Reply with ONLY your conversational answer. No JSON, no metadata, no labels. Just the natural reply text."""

        return system_prompt, user_message

    def _get_personal_memories(self, user) -> str:
        """Get top personal memories for this student, injected into prompt (Redis-cached)."""
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

            if not memories.exists():
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

    def _process_memory_candidates(self, user, message_obj, candidates) -> None:
        """Extract and store durable personal memories from conversation turns.

        Sensitive categories are filtered out by memory_utils.should_store_memory —
        never auto-store health/financial/family/disciplinary details.
        """
        from .models import StudentMemory
        from .memory_utils import should_store_memory

        student = getattr(user, 'student_profile', None)
        if not student:
            return

        if not candidates:
            return

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            key = candidate.get('key', 'context')
            value = candidate.get('value', '')
            confidence = float(candidate.get('confidence', 0.5))

            if not value or not value.strip():
                continue
            if not should_store_memory(key, value):
                logger.info(f"Skipping sensitive memory candidate for user {user.id}: key={key}")
                continue

            # Dedup: if a similar active memory exists, reinforce it
            existing = StudentMemory.objects.filter(
                student=student, key=key, is_active=True
            ).first()
            if existing:
                existing_val = existing.value.lower()
                new_val = value.lower()
                if new_val in existing_val or existing_val in new_val:
                    existing.confidence = min(existing.confidence + 0.1, 1.0)
                    existing.save(update_fields=['confidence', 'last_referenced_at'])
                    continue

            StudentMemory.objects.create(
                student=student,
                key=key,
                value=value.strip(),
                confidence=confidence,
                source_message=message_obj,
            )
            logger.info(f"Stored memory for user {user.id}: {key}")

        # Invalidate personal memory cache so next turn reflects new memories
        try:
            from django.core.cache import cache
            cache.delete(f"personal_mem:{user.id}")
        except Exception:
            pass


    def _get_cache_key(self, user_message: str, conversation_id: str) -> str:
        """Generate cache key for response caching"""
        import hashlib
        # Create a hash of the message and conversation context for caching
        message_hash = hashlib.md5(user_message.encode()).hexdigest()
        return f"chatbot_response_{conversation_id}_{message_hash}"

    def _get_cached_response(self, cache_key: str) -> EnhancedResponse | None:
        """Get cached response if available"""
        from django.core.cache import cache
        cached_data = cache.get(cache_key)
        if cached_data:
            # Reconstruct EnhancedResponse from cached data with complete token tracking
            return EnhancedResponse(
                text=cached_data['reply'],
                current_topic=cached_data['current_topic'],
                topic_summary=cached_data['topic_summary'],
                topic_changed=cached_data['topic_changed'],
                summary=cached_data['summary'],
                personality_notes=cached_data.get('personality_notes'),
                instructions=cached_data.get('instructions'),
                tokens_used=cached_data.get('tokens_used', 0),
                input_tokens=cached_data.get('input_tokens', 0),
                output_tokens=cached_data.get('output_tokens', 0),
                cost_tsh=cached_data.get('cost', 0.0)
            )
        return None

    def _cache_response(self, cache_key: str, response: EnhancedResponse, query_intent: str = "general"):
        """Cache response for future use with smart TTL based on query type"""
        from django.core.cache import cache
        
        # Smart caching: longer TTL for common queries, shorter for personalized/time-sensitive
        has_personal_info = response.personality_notes is not None or response.instructions is not None
        has_schedule_info = 'class' in response.text.lower() or 'today' in response.text.lower()
        
        # Determine cache TTL based on intent and content
        if has_schedule_info:
            ttl = 1800  # 30 minutes for schedule queries
        elif has_personal_info:
            ttl = 3600  # 1 hour for personal responses
        elif query_intent in ['regulation', 'policy', 'procedure']:
            # Regulations and procedures change less frequently
            ttl = 14400  # 4 hours for regulations/procedures
        elif query_intent in ['faq', 'program_info']:
            ttl = 10800  # 3 hours for FAQs and program info
        elif query_intent == 'navigation':
            ttl = 21600  # 6 hours for navigation (rarely changes)
        else:
            ttl = 7200  # 2 hours for general knowledge
        
        cache_data = {
            'reply': response.text,
            'current_topic': response.current_topic,
            'topic_summary': response.topic_summary,
            'topic_changed': response.topic_changed,
            'summary': response.summary,
            'personality_notes': response.personality_notes,
            'instructions': response.instructions,
            'tokens_used': response.tokens_used,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cost': response.cost_tsh,
            'cached_at': datetime.now().isoformat()
        }
        cache.set(cache_key, cache_data, ttl)
        logger.info(f"Response cached with {ttl}s TTL (intent: {query_intent}, personal: {has_personal_info}, schedule: {has_schedule_info})")

    def _extract_json(self, text_str: str) -> Dict:
        """Parse JSON response robustly with multiple fallback methods"""
        # Method 1: Direct parse
        try:
            return json.loads(text_str.strip())
        except Exception:
            pass

        # Method 2: Extract from code blocks
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text_str)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

        # Method 3: Find first balanced JSON object
        start = text_str.find('{')
        if start != -1:
            depth = 0
            for i, ch in enumerate(text_str[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        snippet = text_str[start:i+1]
                        try:
                            return json.loads(snippet)
                        except Exception:
                            break
        return {}

    def _ensure_clean_text(self, text: str) -> str:
        """Guarantee the reply is never raw JSON — always human-readable text."""
        if not text or not text.strip():
            return "I'm having a little trouble finding the right words. Could you rephrase that?"

        stripped = text.strip()

        # If it starts with { it's likely JSON leaked through
        if stripped.startswith('{') and '}' in stripped:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and 'reply' in parsed:
                    return str(parsed['reply'])
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

    def _infer_topic(self, message: str) -> str:
        """Infer a 2-4 word topic from the user message (cheap, no LLM)."""
        lowered = message.lower().strip()
        topic_keywords = {
            'registration': ['register', 'enrollment', 'enroll', 'sign up', 'add course', 'drop course'],
            'exams': ['exam', 'test', 'defer', 'postpone', 'resit'],
            'timetable': ['schedule', 'timetable', 'class', 'classes', 'today'],
            'fees': ['fee', 'fees', 'payment', 'pay', 'tuition', 'cost'],
            'graduation': ['graduate', 'graduation', 'degree', 'certificate'],
            'accommodation': ['hostel', 'accommodation', 'housing', 'room', 'residence'],
            'results': ['result', 'results', 'grade', 'gpa', 'transcript'],
            'courses': ['course', 'unit', 'module', 'credit'],
            'campus': ['campus', 'building', 'office', 'library', 'lab'],
            'general': [],
        }
        for topic, keywords in topic_keywords.items():
            if any(kw in lowered for kw in keywords):
                return topic.title()
        return "General"

    def _detect_topic_change(self, summary: str | None, new_topic: str) -> bool:
        """Detect if the topic changed from the previous conversation summary."""
        if not summary:
            return True
        try:
            data = json.loads(summary)
            topics = data.get("topics", [])
            if topics:
                last_topic = topics[-1].get("topic", "").lower()
                return last_topic != new_topic.lower()
        except Exception:
            pass
        return False

    def _validate_response_quality(self, response_text: str, query: str, rag_context: str = "") -> Dict[str, Any]:
        """Validate response quality and check for potential issues"""
        validation = {
            'is_valid': True,
            'warnings': [],
            'suggestions': []
        }
        
        response_lower = response_text.lower()
        query_lower = query.lower()
        
        # Check if response is too short
        if len(response_text.strip()) < 20:
            validation['warnings'].append('Response is very short')
            validation['is_valid'] = False
        
        # Check if response seems irrelevant (less strict - only flag if really irrelevant)
        # Remove common stop words from keyword matching
        stop_words = {'tell', 'me', 'about', 'the', 'a', 'an', 'to', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'can', 'what', 'where', 'when', 'why', 'how', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'this', 'that', 'these', 'those'}
        query_keywords = set(re.findall(r'\b\w+\b', query_lower)) - stop_words
        response_keywords = set(re.findall(r'\b\w+\b', response_lower)) - stop_words
        common_keywords = query_keywords.intersection(response_keywords)
        
        # Only warn if there are NO meaningful keywords in common (very strict threshold)
        if len(common_keywords) == 0 and len(query_keywords) > 2:
            validation['warnings'].append('Response may not be relevant to query')
        
        # Check for common error phrases
        error_phrases = [
            "i don't know", "i cannot", "i'm unable", "error", "failed",
            "not available", "cannot process"
        ]
        if any(phrase in response_lower for phrase in error_phrases):
            validation['warnings'].append('Response contains error indicators')
        
        # Check if knowledge base was used but response doesn't reference it
        if rag_context and len(rag_context) > 50:
            # Response should be more detailed if knowledge base was provided
            if len(response_text) < 100:
                validation['suggestions'].append('Consider using more knowledge base content')
        
        return validation
    
    def _validate_response_schema(self, parsed: Dict, conversation, text: str) -> Dict:
        """Validate and fix response schema to ensure required fields"""
        required_fields = ["reply", "current_topic", "topic_summary", "topic_changed", "summary"]
        validated = {}

        # Ensure all required fields are present with defaults
        for field in required_fields:
            if field not in parsed or parsed[field] is None:
                if field == "reply":
                    validated[field] = text  # Use raw text as fallback
                elif field == "current_topic":
                    validated[field] = "General"
                elif field == "topic_summary":
                    validated[field] = "General conversation"
                elif field == "topic_changed":
                    validated[field] = False
                elif field == "summary":
                    validated[field] = conversation.summary or "Ongoing conversation"
            else:
                validated[field] = parsed[field]

        # Validate field types and lengths
        if not isinstance(validated["reply"], str) or len(validated["reply"].strip()) < 1:
            validated["reply"] = "I'm not sure how to respond to that. Could you please rephrase your question?"

        if not isinstance(validated["current_topic"], str) or len(validated["current_topic"].strip()) < 1:
            validated["current_topic"] = "General"

        if not isinstance(validated["topic_summary"], str):
            validated["topic_summary"] = "General conversation"

        if not isinstance(validated["topic_changed"], bool):
            validated["topic_changed"] = False

        if not isinstance(validated["summary"], str):
            validated["summary"] = conversation.summary or "Ongoing conversation"

        return validated

    def _throttle_request(self, user_id) -> None:
        """Redis-based per-user rate limiting with burst allowance.

        Allows up to _max_burst requests within the interval window.
        Only blocks (raises) when the burst limit is exceeded.
        """
        from django.core.cache import cache

        max_burst = 5  # Allow up to 5 rapid messages before throttling
        cache_key = f"throttle:user:{user_id}"
        count = cache.get(cache_key, 0)

        if count >= max_burst:
            raise RuntimeError(
                "You're sending messages too fast. Please wait a moment and try again."
            )

        # Increment counter; TTL sets the sliding window
        cache.set(cache_key, count + 1, timeout=int(self._min_request_interval))

    def get_enhanced_response(self, user_message: str, user, conversation, rag_context: str = "", 
                            navigation_context: str = "", intent_info: dict | None = None) -> EnhancedResponse:
        """Get response with memory updates and caching.

        *intent_info*: pre-classified intent dict from the caller (views.py).
        When provided, skips the duplicate classify_query_intent() call.
        """

        # Check cache first for identical queries
        cache_key = self._get_cache_key(user_message, str(conversation.id))
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            logger.info(f"Cache hit for conversation {conversation.id}, user {user.id} - saved API call")
            return cached_response

        logger.info(f"Cache miss for conversation {conversation.id}, user {user.id}, generating new response")

        # Throttle API requests to prevent rate limiting
        self._throttle_request(user.id)

        # Extract personal info from user message first
        personal_info = self._extract_personal_info_from_message(user_message)
        
        # Use pre-classified intent when available, otherwise classify now
        if intent_info is None:
            intent_info = self.classify_query_intent(user_message)
        logger.info(f"Query intent: {intent_info['primary_intent']}, critical: {intent_info['is_critical']}")
        
        system_prompt, formatted_message = self.build_enhanced_prompt(
            user, conversation, user_message, rag_context, personal_info, navigation_context
        )
        
        # Log prompt details only when KB context is present (useful for debugging grounding)
        if rag_context:
            logger.info(f"Prompt sent: {len(system_prompt)} chars, KB={len(rag_context)} chars")
        
        # Call AI API — at most 2 attempts, NO sleeping in the request thread.
        # If the first call fails with a retryable error, try once more immediately.
        # Non-retryable errors (auth, bad key) fail fast.
        max_retries = 2
        timeout_seconds = 20
        resp = None
        last_error = None

        # Token budget: plain text output needs fewer tokens than JSON
        if intent_info.get('is_critical') or intent_info.get('primary_intent') == 'procedure':
            max_tokens = 500
        elif intent_info.get('primary_intent') == 'navigation':
            max_tokens = 250
        else:
            max_tokens = 400

        for attempt in range(max_retries):
            try:
                resp = self._call_llm(
                    system_prompt,
                    formatted_message,
                    max_tokens,
                    timeout_seconds,
                )
                break  # Success

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                logger.warning(f"AI call attempt {attempt + 1}/{max_retries} failed: {error_msg}")

                # Only retry on transient errors (timeout, rate limit, 429)
                is_transient = (
                    "timeout" in error_msg
                    or "rate limit" in error_msg
                    or "too many requests" in error_msg
                    or "429" in error_msg
                )
                if not is_transient or attempt >= max_retries - 1:
                    break  # Don't sleep, don't retry — fail fast

        # Handle failed API calls after all retries
        if resp is None and last_error is not None:
            error_type = type(last_error).__name__
            error_msg = str(last_error).lower()
            logger.error(f"API call failed for user {user.id} after {max_retries} attempts: {error_type} - {error_msg}")

            # Create specific fallback messages based on error type with helpful guidance
            if "authentication" in error_msg or "unauthorized" in error_msg or "invalid" in error_msg:
                fallback_text = "I'm experiencing a configuration issue. Please contact support if this problem persists. In the meantime, you can try asking about general university information."
            elif "rate limit" in error_msg or "quota" in error_msg or "usage" in error_msg:
                fallback_text = "I'm currently at my usage limit. Please try again in a few minutes. For urgent questions, you can check the university website or contact your academic advisor directly."
            elif "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
                fallback_text = "I'm having trouble connecting right now. Please check your internet connection and try again. If the problem persists, you may want to try again later or contact support."
            elif "server" in error_msg or "internal" in error_msg or "500" in error_msg:
                fallback_text = "The AI service is temporarily unavailable. Please try again in a moment. For immediate assistance, you can check the knowledge base or contact your university's student services."
            else:
                # Generic fallback with helpful suggestions
                fallback_text = "I'm having trouble processing your request right now. Please try again in a moment. If this continues, you can:\n- Check the university website for information\n- Contact your academic advisor\n- Try rephrasing your question"

            print(f"Enhanced AI Service Error [{error_type}]: {error_msg}")

            return EnhancedResponse(
                text=fallback_text,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                cost_tsh=0.0,
                summary=conversation.summary or "",
                personality_notes=None,
                instructions=None,
                current_topic=None,
                topic_changed=False,
                topic_summary=None,
            )
        
        # Extract text — LLM now returns plain conversational reply (no JSON)
        text_parts: List[str] = []
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", ""))
        raw_text = "".join(text_parts) or "Sorry, I couldn't generate a response now."

        # Strip any accidental JSON/structured wrapper the model might still produce.
        # The model is instructed to return plain text, but some models occasionally
        # wrap output in ```json blocks or similar. Handle the common cases:
        reply = raw_text.strip()

        # Remove markdown code fences if present
        if reply.startswith("```"):
            # Strip opening fence (```json or ``` etc.)
            first_newline = reply.find("\n")
            if first_newline != -1:
                reply = reply[first_newline + 1:]
            # Strip closing fence
            if reply.endswith("```"):
                reply = reply[:-3].strip()

        # If the model still returned JSON despite instructions, extract "reply" field
        if reply.startswith("{") and "reply" in reply:
            parsed = self._extract_json(reply)
            if parsed and isinstance(parsed, dict) and "reply" in parsed:
                reply = str(parsed["reply"])
            else:
                # Last resort — just use the raw text
                reply = raw_text.strip()

        # GUARANTEED CLEAN TEXT — never let raw JSON reach the student
        reply = self._ensure_clean_text(reply)

        # Log the actual response for debugging
        logger.info(f"AI RESPONSE RECEIVED — length: {len(reply)} chars")
        if rag_context:
            logger.info(f"Knowledge base was provided: {len(rag_context)} chars")

        # --- Metadata extraction (heuristic, no LLM call needed) ---
        current_topic = self._infer_topic(user_message)
        topic_changed = self._detect_topic_change(conversation.summary, current_topic)
        topic_summary = user_message[:100]

        # Personal info / instructions — extract from the user message, not from LLM JSON
        personality_notes = personal_info if personal_info else None
        instructions = None  # Could be extracted with heuristics if needed

        # Memory candidates — extract durable facts from user message
        memory_candidates = []
        durable_facts = self._extract_personal_info_from_message(user_message)
        if durable_facts:
            memory_candidates = [{"key": "context", "value": durable_facts, "confidence": 0.6}]

        # Validate response quality
        quality_check = self._validate_response_quality(reply, user_message, rag_context)
        if quality_check['warnings']:
            logger.warning(f"Response quality warnings for user {user.id}: {quality_check['warnings']}")
        if quality_check['suggestions']:
            logger.debug(f"Response quality suggestions: {quality_check['suggestions']}")
        
        # Get token usage
        input_tokens = 0
        output_tokens = 0
        try:
            ui = getattr(resp, "usage", None)
            if ui:
                input_tokens = int(getattr(ui, "input_tokens", 0))
                output_tokens = int(getattr(ui, "output_tokens", 0))
        except Exception:
            input_tokens = 0
            output_tokens = 0

        # Cost calculation in TSH
        input_usd = input_tokens * float(getattr(settings, "ANTHROPIC_INPUT_USD_PER_TOKEN", 0.00000025))
        output_usd = output_tokens * float(getattr(settings, "ANTHROPIC_OUTPUT_USD_PER_TOKEN", 0.00000125))
        total_usd = input_usd + output_usd
        rate = float(getattr(settings, "USD_TO_TSH_RATE", 2700))
        cost_tsh = round(total_usd * rate, 2)

        # Build hierarchical topic summary (lightweight, no LLM needed)
        summary_json = conversation.summary or ""
        try:
            data = json.loads(summary_json) if summary_json else {}
        except Exception:
            data = {}
        topics = data.get("topics", [])

        if current_topic:
            if not topics or topic_changed:
                topics.append({
                    "topic": current_topic,
                    "summary": topic_summary or "",
                    "message_count": 1,
                    "started_at": timezone.now().isoformat(),
                })
            else:
                cur = topics[-1]
                cur["message_count"] = int(cur.get("message_count", 0)) + 1
                if topic_summary and topic_summary not in (cur.get("summary") or ""):
                    cur["summary"] = f"{cur.get('summary','')} {topic_summary}".strip()
            if len(topics) > 5:
                topics = topics[-5:]
            super_summary = " → ".join([t.get("topic", "?") for t in topics])
            data = {
                "super_summary": super_summary,
                "topics": topics,
                "total_messages": sum(int(t.get("message_count", 0)) for t in topics),
                "last_updated": timezone.now().isoformat(),
            }
            summary_json = json.dumps(data, ensure_ascii=False)

        # Create response object
        response = EnhancedResponse(
            text=reply,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_tsh=cost_tsh,
            summary=summary_json,
            personality_notes=personality_notes,
            instructions=instructions,
            current_topic=current_topic,
            topic_changed=topic_changed,
            topic_summary=topic_summary,
            memory_candidates=memory_candidates,
        )

        # Cache the response for future use (with intent for better TTL)
        self._cache_response(cache_key, response, intent_info.get('primary_intent', 'general'))
        logger.info(f"Response cached for conversation {conversation.id}, tokens: {response.tokens_used}")

        return response

    def get_enhanced_response_streaming(self, user_message: str, user, conversation,
                                        rag_context: str = "", navigation_context: str = "",
                                        intent_info: dict | None = None):
        """Streaming version — yields text chunks as they're generated.

        Yields dicts with keys:
          - type='text', content=<chunk>
          - type='meta', tokens_used=<int>, cost_tsh=<float>, reply=<full text>
        The final 'meta' event is always yielded last so the caller can persist.
        """
        # Check cache first — on hit, emit the cached reply in one chunk
        cache_key = self._get_cache_key(user_message, str(conversation.id))
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            logger.info(f"Cache hit (stream) for conversation {conversation.id}")
            yield {"type": "text", "content": cached_response.text}
            yield {
                "type": "meta",
                "tokens_used": cached_response.tokens_used,
                "cost_tsh": cached_response.cost_tsh,
                "reply": cached_response.text,
            }
            return

        # Throttle
        self._throttle_request(user.id)

        personal_info = self._extract_personal_info_from_message(user_message)
        if intent_info is None:
            intent_info = self.classify_query_intent(user_message)

        system_prompt, formatted_message = self.build_enhanced_prompt(
            user, conversation, user_message, rag_context, personal_info, navigation_context
        )

        # Token budget
        if intent_info.get('is_critical') or intent_info.get('primary_intent') == 'procedure':
            max_tokens = 500
        elif intent_info.get('primary_intent') == 'navigation':
            max_tokens = 250
        else:
            max_tokens = 400

        full_text = ""
        try:
            for chunk in self._call_llm_streaming(system_prompt, formatted_message, max_tokens, 20):
                full_text += chunk
                yield {"type": "text", "content": chunk}
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Streaming LLM call failed: {error_msg}")
            fallback = "I'm having trouble connecting right now. Please try again in a moment."
            yield {"type": "text", "content": fallback}
            full_text = fallback

        # Ensure clean text
        full_text = self._ensure_clean_text(full_text)

        # Token usage (approximate for streaming — exact count not always available)
        input_tokens = 0
        output_tokens = max(len(full_text.split()) * 1.3, 1)  # rough estimate
        total_tokens = int(input_tokens + output_tokens)
        input_usd = input_tokens * float(getattr(settings, "ANTHROPIC_INPUT_USD_PER_TOKEN", 0.00000025))
        output_usd = output_tokens * float(getattr(settings, "ANTHROPIC_OUTPUT_USD_PER_TOKEN", 0.00000125))
        rate = float(getattr(settings, "USD_TO_TSH_RATE", 2700))
        cost_tsh = round((input_usd + output_usd) * rate, 2)

        # Build metadata
        current_topic = self._infer_topic(user_message)
        topic_changed = self._detect_topic_change(conversation.summary, current_topic)
        topic_summary = user_message[:100]

        # Summary
        summary_json = conversation.summary or ""
        try:
            data = json.loads(summary_json) if summary_json else {}
        except Exception:
            data = {}
        topics = data.get("topics", [])
        if current_topic:
            if not topics or topic_changed:
                topics.append({
                    "topic": current_topic,
                    "summary": topic_summary,
                    "message_count": 1,
                    "started_at": timezone.now().isoformat(),
                })
            else:
                cur = topics[-1]
                cur["message_count"] = int(cur.get("message_count", 0)) + 1
            if len(topics) > 5:
                topics = topics[-5:]
            super_summary = " → ".join([t.get("topic", "?") for t in topics])
            data = {
                "super_summary": super_summary,
                "topics": topics,
                "total_messages": sum(int(t.get("message_count", 0)) for t in topics),
                "last_updated": timezone.now().isoformat(),
            }
            summary_json = json.dumps(data, ensure_ascii=False)

        response = EnhancedResponse(
            text=full_text,
            tokens_used=total_tokens,
            input_tokens=input_tokens,
            output_tokens=int(output_tokens),
            cost_tsh=cost_tsh,
            summary=summary_json,
            personality_notes=personal_info if personal_info else None,
            instructions=None,
            current_topic=current_topic,
            topic_changed=topic_changed,
            topic_summary=topic_summary,
            memory_candidates=[{"key": "context", "value": personal_info, "confidence": 0.6}] if personal_info else [],
        )

        self._cache_response(cache_key, response, intent_info.get('primary_intent', 'general'))

        yield {
            "type": "meta",
            "tokens_used": total_tokens,
            "cost_tsh": cost_tsh,
            "reply": full_text,
        }

    def _clean_personality_notes(self, notes: str) -> str:
        """Clean and deduplicate personality notes"""
        if not notes:
            return ""
        
        # Split by bullet points and clean
        lines = [line.strip() for line in notes.split('\n') if line.strip()]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_lines = []
        for line in lines:
            # Remove bullet point if present
            clean_line = line.lstrip('•').strip()
            if clean_line and clean_line not in seen:
                seen.add(clean_line)
                unique_lines.append(f"• {clean_line}")
        
        return '\n'.join(unique_lines)

    def update_memory(self, user, conversation, response: EnhancedResponse):
        """Update conversation summary and chat history"""
        
        try:
            # Update conversation summary
            if response.summary:
                conversation.summary = response.summary
                conversation.save(update_fields=['summary'])
            
            # Update ChatHistory if new info provided
            from django.db import transaction
            
            with transaction.atomic():
                chat_history, _ = ChatHistory.objects.get_or_create(user=user)
                    
                # Debug: Print what we're trying to save
                logger.info(f"Memory update - personality_notes: {response.personality_notes is not None}, instructions: {response.instructions is not None}")
                    
                updated = False
                
                if response.personality_notes:
                    # Clean and deduplicate personality notes
                    existing = chat_history.personality_notes or ""
                    new_note = response.personality_notes.strip()
                    
                    # Add new note to existing ones
                    if existing:
                        combined_notes = f"{existing}\n• {new_note}"
                    else:
                        combined_notes = f"• {new_note}"
                    
                    # Clean and deduplicate the combined notes
                    cleaned_notes = self._clean_personality_notes(combined_notes)
                    
                    if cleaned_notes != existing:
                        chat_history.personality_notes = cleaned_notes
                        updated = True
                        logger.info(f"Updated personality notes for user {user.id}")
                    else:
                        logger.info(f"Skipped duplicate personality note for user {user.id}")
                
                if response.instructions:
                    # Clean and deduplicate instructions
                    existing = chat_history.instructions or ""
                    new_instruction = response.instructions.strip()
                    
                    # Add new instruction to existing ones
                    if existing:
                        combined_instructions = f"{existing}\n• {new_instruction}"
                    else:
                        combined_instructions = f"• {new_instruction}"
                    
                    # Clean and deduplicate the combined instructions
                    cleaned_instructions = self._clean_personality_notes(combined_instructions)
                    
                    if cleaned_instructions != existing:
                        chat_history.instructions = cleaned_instructions
                        updated = True
                        logger.info(f"Updated instructions for user {user.id}")
                    else:
                        logger.info(f"Skipped duplicate instruction for user {user.id}")
                
                if updated:
                    chat_history.save()
                    logger.info(f"ChatHistory saved successfully for user {user.id}")
                    
        except Exception as e:
            logger.error(f"Error in update_memory for user {user.id}: {e}")
            # Don't raise the exception to avoid breaking the main flow

    def should_use_quick_response(self, query: str, conversation_message_count: int) -> Optional[str]:
        """Determine if query can be answered with a quick response (no API call)
        
        Returns:
            query_type if quick response should be used, None otherwise
        """
        if not query:
            return None
            
        lowered = query.strip().lower()
        
        # Only use quick greeting in first 2 messages
        if conversation_message_count <= 2 and len(lowered) <= 15 and re.match(r"^(hi|hello|hey)\b", lowered):
            return "greeting"
        
        # Schedule queries - always quick response
        if any(keyword in lowered for keyword in ["schedule today", "today's classes", "classes today", "what's my schedule"]):
            return "schedule_today"
        
        if "next class" in lowered:
            return "next_class"
        
        # AutoCAD queries - use quick response for basic shortcuts
        autocad_keywords = ["autocad shortcuts", "cad shortcuts", "autocad commands", "cad commands", "autocad basic"]
        if any(keyword in lowered for keyword in autocad_keywords):
            return "autocad"
        
        return None
    
    def get_quick_response(self, query_type: str, user) -> str:
        """Quick responses without API calls"""
        qt = (query_type or "").lower()
        student: Student | None = getattr(user, "student_profile", None)
        
        if qt == "greeting":
            name = getattr(user, "display_name", "there")
            return f"Hey {name}! How can I help today? 📚"
        
        if qt in ("schedule_today", "schedule"):
            if not student:
                return "I couldn't find your profile to fetch today's classes."
            today = timezone.now().strftime("%A").lower()
            slots = TimetableSlot.objects.filter(student=student, day_of_week=today).order_by("time_slot")
            if not slots.exists():
                return "No classes scheduled for today. ✅"
            lines = ["Today's classes:"]
            for t in slots:
                lines.append(f"- {t.course_code or t.course_name or t.course} at {t.time_slot} in {t.venue}")
            lines.append("[LINK:/app/timetable]")
            return "\n".join(lines)
        
        if qt == "next_class":
            if not student:
                return "I couldn't find your profile to fetch the next class."
            now_hhmm = timezone.now().strftime("%H%M")
            today = timezone.now().strftime("%A").lower()
            slots = TimetableSlot.objects.filter(student=student, day_of_week=today).order_by("time_slot")
            upcoming = None
            for s in slots:
                start = (s.time_slot or "0000-0000").split("-")[0]
                if start >= now_hhmm:
                    upcoming = s
                    break
            if not upcoming:
                return "No more classes today. 🎯"
            return f"Next class: {upcoming.course_code or upcoming.course_name or upcoming.course} at {upcoming.time_slot} in {upcoming.venue}. [LINK:/app/timetable]"
        
        if qt == "assignments":
            return "You have no tracked assignments yet. Want me to set a reminder? [ACTION:set_reminder]"
        
        # Check for AutoCAD-related queries
        autocad_keywords = ["autocad", "cad", "drafting", "design software", "shortcuts", "commands"]
        if qt and any(keyword in qt for keyword in autocad_keywords):
            return """Here are essential AutoCAD shortcuts for house design:

**Basic Commands:**
- L = Line
- C = Circle  
- R = Rectangle
- TR = Trim
- EX = Extend
- X = Explode
- CO = Copy
- M = Move
- RO = Rotate
- SC = Scale
**Modify Commands:**
- F = Fillet
- CHA = Chamfer
- MI = Mirror
- AR = Array
- O = Offset
- S = Stretch

**View Commands:**
- Z = Zoom
- P = Pan
- RE = Regen
- V = View

**Layers & Properties:**
- LA = Layer Manager
- MA = Match Properties
- CH = Properties

**Quick Tips:**
- Spacebar = Repeat last command
- Ctrl+Z = Undo
- Ctrl+Y = Redo
- ESC = Cancel current command

Happy designing! 🏗️"""
        
        return "I'm here to help! Ask me about your schedule, courses, or campus."
