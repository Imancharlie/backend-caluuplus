from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
import logging

from anthropic import Anthropic

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


class EnhancedClaudeService:
    """Enhanced Claude service with hierarchical memory and topic tracking"""
    
    def __init__(self) -> None:
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

        self._model = "claude-3-haiku-20240307"
        self._client = Anthropic(api_key=api_key)
        
        # Rate limiting: Track last request time to prevent API rate limits
        self._last_request_time = None
        # Free tier: 5 req/min = 12s interval, Paid: 50 req/min = 1.2s interval
        self._min_request_interval = float(getattr(settings, 'ANTHROPIC_MIN_REQUEST_INTERVAL', 12))
        
        logger.info(f"EnhancedClaudeService initialized with {self._min_request_interval}s request interval")

    def build_student_context(self, user) -> str:
        """Build comprehensive student context from existing models"""
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
                    for c in student_courses.courses:
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
        return "\n".join(lines)

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
        """Build comprehensive prompt with hierarchical memory, personalization, and academic advisor persona"""
        
        # Get or create ChatHistory
        chat_history, _ = ChatHistory.objects.get_or_create(user=user)
        
        # Get last 2 message pairs for immediate context
        recent_messages = conversation.messages.order_by('-timestamp')[:4]
        recent_context = self._format_recent_messages(recent_messages)
        
        # Build student context
        student_context = self.build_student_context(user)
        
        # Topics from hierarchical summary
        topics = self._parse_topic_segments(conversation.summary)
        topics_formatted = self._format_topic_segments(topics)

        # Format RAG context - put it FIRST and make it impossible to ignore
        if rag_context:
            # Put knowledge base at the very top of the prompt
            rag_section = f"""
╔═══════════════════════════════════════════════════════════════╗
║                    KNOWLEDGE BASE - REQUIRED                  ║
║         YOU MUST USE THIS INFORMATION TO ANSWER               ║
╚═══════════════════════════════════════════════════════════════╝

{rag_context}

╔═══════════════════════════════════════════════════════════════╗
║                    CRITICAL: READ THIS                        ║
╚═══════════════════════════════════════════════════════════════╝

The knowledge base above contains the EXACT answer to the student's question.
Your response MUST be based on this knowledge base content.

FORBIDDEN RESPONSES (DO NOT USE THESE):
- "I'm here to help! What would you like to know?"
- "How can I help you today?"
- "I can help you with that!"
- Any generic greeting or offer to help

REQUIRED: Extract the relevant information from the knowledge base and present it directly to the student.
"""
        else:
            rag_section = ""
        
        nav_section = f"\nNAVIGATION:\n{navigation_context}\n" if navigation_context else ""
        
        # Put knowledge base FIRST, then persona
        if rag_context:
            system_prompt = f"""{rag_section}

You are MR CALUU, an intelligent academic advisor and trusted friend to university students.

STUDENT'S QUESTION: "{user_message}"

YOUR TASK: Answer the question above using the knowledge base information provided. Extract and present the relevant information from the knowledge base.

STUDENT PROFILE:
{student_context}

PERSONAL CONTEXT:
Personality Notes: {chat_history.personality_notes or 'None'}
User Preferences: {chat_history.instructions or 'None'}
New Information: {personal_info or 'None'}

CONVERSATION CONTEXT:
Recent Topics: {topics_formatted}
Recent Messages: {recent_context}
{nav_section}
RESPONSE FORMAT (JSON ONLY):
{{
  "reply": "Your response based on the knowledge base. Extract information from the knowledge base and present it clearly. For procedures, list the steps. DO NOT give generic responses.",
  "current_topic": "2-4 word topic identifier",
  "topic_summary": "Brief 1 sentence summary of current topic",
  "topic_changed": boolean,
  "personality_notes": "New personal information to remember|null",
  "instructions": "New user preferences to remember|null",
  "summary": "2-3 sentence conversation summary"
}}

CRITICAL RULES:
1. Your reply MUST use the knowledge base information provided above
2. Extract and present the information from the knowledge base
3. DO NOT give generic responses - use the knowledge base content
4. Answer the specific question: "{user_message}"
5. Always respond in JSON format only"""
        else:
            # No knowledge base - use normal prompt
            system_prompt = f"""You are MR CALUU, an intelligent academic advisor and trusted friend to university students. You are knowledgeable, supportive, professional yet friendly, and deeply familiar with university regulations, procedures, and academic life.

YOUR ROLE:
- Academic advisor providing guidance on university regulations, procedures, and policies
- Navigation assistant helping students find features and pages in Caluu+
- Academic supervisor offering study advice and course guidance
- Trusted source of information about university life, rules, and procedures
- Friendly companion who remembers student preferences and personal context

STUDENT PROFILE:
{student_context}

PERSONAL CONTEXT:
Personality Notes: {chat_history.personality_notes or 'None'}
User Preferences: {chat_history.instructions or 'None'}
New Information: {personal_info or 'None'}

CONVERSATION CONTEXT:
Recent Topics: {topics_formatted}
Recent Messages: {recent_context}
{nav_section}
RESPONSE FORMAT (JSON ONLY):
{{
  "reply": "Your response to the student. Be helpful, accurate, and specific.",
  "current_topic": "2-4 word topic identifier",
  "topic_summary": "Brief 1 sentence summary of current topic",
  "topic_changed": boolean,
  "personality_notes": "New personal information to remember|null",
  "instructions": "New user preferences to remember|null",
  "summary": "2-3 sentence conversation summary"
}}

IMPORTANT RULES:
1. Always respond in JSON format only
2. Be professional yet warm and supportive
3. If you don't know something, admit it and suggest where to find the information"""
        
        return system_prompt, user_message

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
        """Throttle API requests to respect rate limits with per-user tracking"""
        # Use per-user throttling instead of global throttling
        # This allows multiple users to use the chatbot simultaneously
        from django.core.cache import cache
        
        cache_key = f"last_request_user_{user_id}"
        last_request = cache.get(cache_key)
        
        if last_request:
            elapsed = (datetime.now() - datetime.fromisoformat(last_request)).total_seconds()
            if elapsed < self._min_request_interval:
                wait_time = self._min_request_interval - elapsed
                # OPTIMIZATION: Only throttle if wait time is significant (> 0.3s instead of 0.5s)
                if wait_time > 0.3:
                    logger.info(f"Throttling request for user {user_id}, waiting {wait_time:.1f}s to respect rate limits")
                    time.sleep(wait_time)
        
        # Store the request time for this user (expires after interval + buffer)
        cache.set(cache_key, datetime.now().isoformat(), self._min_request_interval + 5)

    def get_enhanced_response(self, user_message: str, user, conversation, rag_context: str = "", 
                            navigation_context: str = "") -> EnhancedResponse:
        """Get response with memory updates and caching"""

        # Check cache first for identical queries
        cache_key = self._get_cache_key(user_message, str(conversation.id))
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            # Log cache hit for metrics
            logger.info(f"Cache hit for conversation {conversation.id}, user {user.id} - saved API call")
            return cached_response

        logger.info(f"Cache miss for conversation {conversation.id}, user {user.id}, generating new response")

        # Throttle API requests to prevent rate limiting
        self._throttle_request(user.id)

        # Extract personal info from user message first
        personal_info = self._extract_personal_info_from_message(user_message)
        
        # Classify query intent for better routing
        intent_info = self.classify_query_intent(user_message)
        logger.info(f"Query intent: {intent_info['primary_intent']}, critical: {intent_info['is_critical']}")
        
        system_prompt, formatted_message = self.build_enhanced_prompt(
            user, conversation, user_message, rag_context, personal_info, navigation_context
        )
        
        # Log the prompt being sent (for debugging)
        if rag_context:
            logger.info(f"📤 PROMPT BEING SENT TO AI")
            logger.info(f"   System prompt length: {len(system_prompt)} chars")
            logger.info(f"   User prompt: {formatted_message[:100]}...")
            logger.info(f"   Knowledge base in prompt: {'YES' if rag_context in system_prompt else 'NO'}")
            # Show a snippet of the system prompt to verify knowledge base is there
            kb_start = system_prompt.find("KNOWLEDGE BASE")
            if kb_start != -1:
                logger.info(f"   Knowledge base starts at position: {kb_start}")
                logger.info(f"   KB snippet: {system_prompt[kb_start:kb_start+300]}...")
            else:
                logger.error(f"   ❌ KNOWLEDGE BASE NOT FOUND IN PROMPT!")
        
        # Call Claude API with timeout handling and retry logic
        max_retries = 3
        timeout_seconds = 20  # Reduced from 30 for faster responses
        resp = None
        last_error = None

        for attempt in range(max_retries):
            try:
                # OPTIMIZATION: Use already classified intent instead of re-classifying
                # Intent was already classified in views.py, but we need it here too
                # For now, we'll keep it but could pass it as parameter to avoid duplicate work
                if intent_info.get('is_critical') or intent_info.get('primary_intent') == 'procedure':
                    max_tokens = 800  # More tokens for critical/procedure queries
                elif intent_info.get('primary_intent') == 'navigation':
                    max_tokens = 400  # Less tokens for simple navigation
                else:
                    max_tokens = 600  # Default
                
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": formatted_message
                    }],
                    timeout=timeout_seconds
                )
                break  # Success, exit retry loop

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                print(f"API call attempt {attempt + 1} failed: {error_msg}")

                # Check if it's a timeout or rate limit error that we should retry
                if attempt < max_retries - 1 and (
                    "timeout" in error_msg or
                    "rate limit" in error_msg or
                    "too many requests" in error_msg or
                    "429" in error_msg
                ):
                    import time
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = (2 ** attempt)
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue

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
        
        # Extract text
        text_parts: List[str] = []
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts) or "Sorry, I couldn't generate a response now."
        
        parsed = self._extract_json(text)

        # Validate and fix response schema
        if parsed and isinstance(parsed, dict):
            parsed = self._validate_response_schema(parsed, conversation, text)

        # Extract fields with better fallbacks
        if parsed and isinstance(parsed, dict):
            # Always extract just the reply field from JSON
            reply = str(parsed.get("reply", ""))
            
            # Log the actual response for debugging
            logger.info(f"📝 AI RESPONSE RECEIVED")
            logger.info(f"   Length: {len(reply)} chars")
            logger.info(f"   Preview: {reply[:150]}...")
            if rag_context:
                logger.info(f"   Knowledge base was provided: {len(rag_context)} chars")
            
            # Check if reply is generic and knowledge base was provided
            generic_phrases = [
                "i'm here to help",
                "what would you like to know",
                "how can i help",
                "i can help you",
                "feel free to ask",
                "i'm here as your",
                "how can i assist"
            ]
            reply_lower = reply.lower()
            is_generic = any(phrase in reply_lower for phrase in generic_phrases) and len(reply.strip()) < 150
            
            if is_generic and rag_context and len(rag_context) > 50:
                logger.error(f"❌ GENERIC RESPONSE DETECTED despite knowledge base being available!")
                logger.error(f"   Full Reply: '{reply}'")
                logger.error(f"   RAG context was {len(rag_context)} chars")
                logger.error(f"   This indicates the AI is ignoring the knowledge base!")
                # Try to extract useful info from knowledge base as fallback
                # This shouldn't happen, but if it does, we'll log it
            
            # If reply is empty or missing, try to extract from text
            if not reply or len(reply.strip()) < 3:
                # Try to find reply in the raw text
                if "\"reply\":" in text or "'reply':" in text:
                    # JSON exists but parsing failed, try manual extraction
                    # Use top-level re import (line 4)
                    match = re.search(r'"reply"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text, re.DOTALL)
                    if match:
                        reply = match.group(1).replace('\\"', '"').replace('\\n', '\n')
                    else:
                        # Use raw text as last resort
                        reply = text
                else:
                    reply = text
            
            current_topic = parsed.get("current_topic")
            topic_summary = parsed.get("topic_summary", "")
            topic_changed = bool(parsed.get("topic_changed", False))
            summary = str(parsed.get("summary", conversation.summary or ""))
            personality_notes = parsed.get("personality_notes")
            instructions = parsed.get("instructions")
        else:
            # Fallback: use raw text as reply, maintain conversation context
            reply = text
            current_topic = "General"
            topic_summary = "User query and response"
            topic_changed = False
            summary = conversation.summary or ""
            personality_notes = None
            instructions = None
                
            # Try to extract personal information from the AI response even if JSON parsing failed
            if any(keyword in text.lower() for keyword in ["girlfriend", "boyfriend", "wife", "husband", "family", "mother", "father", "sister", "brother", "friend", "relationship", "dating", "married"]):
                personality_notes = f"Personal info mentioned: {text[:200]}..."
            elif personal_info:
                # Use detected personal info from user message
                personality_notes = f"User shared: {personal_info}"
        
        # Ensure reply is clean (no JSON artifacts)
        # Check if the reply still contains JSON structure
        reply_stripped = reply.strip()
        if reply_stripped.startswith('{') and reply_stripped.endswith('}'):
            # The entire reply is JSON, extract the actual reply text
            try:
                json_reply = json.loads(reply_stripped)
                if isinstance(json_reply, dict) and "reply" in json_reply:
                    reply = json_reply["reply"]
                else:
                    # Fallback to helpful message
                    reply = "I'm here to help! What would you like to know?"
            except:
                reply = "I'm here to help! What would you like to know?"
        
        # Remove any leading/trailing JSON markers that might have slipped through
        reply = re.sub(r'^[\{\[].*?"reply"\s*:\s*"', '', reply)
        reply = re.sub(r'",?\s*"current_topic".*[\}\]]$', '', reply)
        reply = reply.strip()
        
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

        # Build hierarchical topic summary when data present
        def _build_summary(existing: str, topic: Optional[str], t_summary: str, changed: bool) -> str:
            try:
                data = json.loads(existing or "{}")
            except Exception:
                data = {}
            topics = data.get("topics", [])
            if topic or t_summary:
                if not topics or changed:
                    topics.append({
                        "topic": topic or "General",
                        "summary": t_summary or "",
                        "message_count": 1,
                        "started_at": timezone.now().isoformat(),
                    })
                else:
                    cur = topics[-1]
                    cur["message_count"] = int(cur.get("message_count", 0)) + 1
                    if t_summary and t_summary not in (cur.get("summary") or ""):
                        cur["summary"] = f"{cur.get('summary','')} {t_summary}".strip()
                if len(topics) > 5:
                    topics = topics[-5:]
                super_summary = " → ".join([t.get("topic", "?") for t in topics])
                data = {
                    "super_summary": super_summary,
                    "topics": topics,
                    "total_messages": sum(int(t.get("message_count", 0)) for t in topics),
                    "last_updated": timezone.now().isoformat(),
                }
                return json.dumps(data, ensure_ascii=False)
            return existing or ""

        summary_json = _build_summary(summary, current_topic, topic_summary, topic_changed)

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
        )

        # Cache the response for future use (with intent for better TTL)
        intent_info = self.classify_query_intent(user_message)
        self._cache_response(cache_key, response, intent_info.get('primary_intent', 'general'))
        logger.info(f"Response cached for conversation {conversation.id}, tokens: {response.tokens_used}")

        return response

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
