from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import re
from django.conf import settings
from django.utils import timezone

from anthropic import Anthropic

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


class EnhancedClaudeService:
    """Enhanced Claude service with memory and summarization"""
    
    def __init__(self) -> None:
        api_key = (
            getattr(settings, "ANTHROPIC_API_KEY", "")
            or settings.ANTHROPIC_API_KEY
        )
        if not api_key:
            raise RuntimeError("Anthropic API key not configured. Set ANTHROPIC_API_KEY in settings or environment.")

        self._model = "claude-3-haiku-20240307"
        self._client = Anthropic(api_key=api_key)

    def build_student_context(self, user) -> str:
        """Build student context from existing models"""
        lines: List[str] = []
        student: Student | None = getattr(user, "student_profile", None)
        if student:
            lines.append(f"Student: {user.display_name} | Email: {user.email}")
            lines.append(
                f"Programme: {student.program.name} | College: {student.college.name} | University: {student.university.name}"
            )
            lines.append(f"Year: {student.year} | Semester: {student.semester}")

            try:
                student_courses: StudentCourse | None = getattr(student, "student_courses", None)
                if student_courses and student_courses.courses:
                    compact = []
                    for _key, items in student_courses.get_periods().items():
                        for c in items:
                            code = c.get("code") or c.get("course_code") or "?"
                            name = c.get("name") or c.get("course_name") or "Course"
                            compact.append(f"{code}:{name}")
                    lines.append("Courses: " + ", ".join(compact))
            except Exception:
                pass

            today = timezone.now().strftime("%A").lower()
            today_classes = TimetableSlot.objects.filter(student=student, day_of_week=today).order_by("time_slot")
            if today_classes.exists():
                lines.append("Today:")
                for t in today_classes:
                    lines.append(f" - {t.course_code or t.course_name or t.course} {t.time_slot} {t.venue} (Instructor: {t.instructor_name})")

        unread = Notification.objects.filter(user=user, read_at__isnull=True).count()
        if unread:
            lines.append(f"Unread notifications: {unread}")
        return "\n".join(lines)

    def _format_recent_messages(self, messages) -> str:
        """Format last few messages for context"""
        if not messages:
            return "[No previous messages]"
        
        formatted = []
        for msg in reversed(messages):
            role = "User" if msg.role == "user" else "Mr. Caluu"
            formatted.append(f"{role}: {msg.content[:100]}...")
        
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
        """Format topic segments for prompt"""
        if not topics:
            return "[No previous topics]"
        lines: List[str] = []
        for i, t in enumerate(topics[-3:], 1):
            lines.append(f"{i}. {t.get('topic','General')} ({t.get('message_count',0)} msgs): {t.get('summary','')}")
        return "\n".join(lines)

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

    def build_enhanced_prompt(self, user, conversation, user_message: str, rag_context: str = "", personal_info: str = "") -> Tuple[str, str]:
        """Build comprehensive prompt with memory and personalization"""
        
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

        rag_section = f"\n{rag_context}\n" if rag_context else ""
        
        system_prompt = f"""You are Mr. Caluu, a charming, witty, teasing, and supportive academic assistant.
Personality: Friendly, respectful teasing, encouraging, concise, adaptive.

STUDENT INFORMATION:
{student_context}

USER PERSONALITY & NOTES:
{chat_history.personality_notes or '[No personality notes yet]'}

USER PREFERENCES & INSTRUCTIONS:
{chat_history.instructions or '[No special instructions]'}

DETECTED PERSONAL INFO IN THIS MESSAGE:
{personal_info or '[No personal info detected]'}

CONVERSATION TOPICS:
{topics_formatted}

RECENT CONTEXT (Last 2 exchanges):
{recent_context}
{rag_section}
RESPONSE FORMAT (JSON only):
{{
  "reply": "Your conversational response",
  "current_topic": "2-4 word topic of THIS exchange",
  "topic_summary": "1-sentence summary of THIS exchange",
  "topic_changed": true/false,
  "personality_notes": "NEW personal info or null",
  "instructions": "NEW user prefs or null",
  "summary": "Updated overall conversation summary (2-3 sentences)"
}}

IMPORTANT: 
- If user shares personal info (relationships, family, hobbies, preferences, habits), put it in "personality_notes"
- If user gives specific instructions (language, nickname, tone), put it in "instructions"
- ALWAYS return valid JSON - no markdown, no extra text
- Example personality_notes: "Has a girlfriend named Sarah, likes morning coffee, studies architecture"
- Example instructions: "Call me Boss, speak in Kiswahili, be more formal"

Rules:
1) Return ONLY JSON (no markdown).
2) Be warm and helpful; use emojis sparingly.
3) Use [LINK:/app/key] when relevant."""
        
        return system_prompt, user_message

    def get_enhanced_response(self, user_message: str, user, conversation, rag_context: str = "") -> EnhancedResponse:
        """Get response with memory updates"""
        
        # Extract personal info from user message first
        personal_info = self._extract_personal_info_from_message(user_message)
        
        system_prompt, formatted_message = self.build_enhanced_prompt(
            user, conversation, user_message, rag_context, personal_info
        )
        
        # Call Claude API with error handling
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                temperature=0.2,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": formatted_message
                }]
            )
        except Exception as e:
            # Return fallback response on API error
            return EnhancedResponse(
                text=f"Sorry, I'm having trouble connecting right now. Please try again in a moment. If this persists, check your internet connection.",
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                cost_tsh=0.0,
                summary=conversation.summary or "",
                personality_notes=None,
                instructions=None,
                current_topic=None,
                topic_changed=False,
            )
        
        # Extract text
        text_parts: List[str] = []
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts) or "Sorry, I couldn't generate a response now."
        
        # Parse JSON response robustly
        def _extract_json(text_str: str) -> Dict:
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

        parsed = _extract_json(text)
        
        # Extract fields with better fallbacks
        if parsed and isinstance(parsed, dict):
            reply = str(parsed.get("reply", text))
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
            
            # If the AI response looks like it might be helpful, use it
            if "autocad" in text.lower() or "shortcuts" in text.lower():
                # Don't override helpful responses
                pass
            elif len(text) < 50 and "help" in text.lower():
                # Generic responses get replaced
                reply = "I'm here to help! What would you like to know? 📚"
        
        # Ensure reply is clean (no JSON artifacts)
        if reply.strip().startswith('{') and reply.strip().endswith('}'):
            reply = "I'm here to help! What would you like to know? 📚"
        
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

        return EnhancedResponse(
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
        )

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
            chat_history, _ = ChatHistory.objects.get_or_create(user=user)
            
            # Debug: Print what we're trying to save
            print(f"DEBUG: personality_notes = {response.personality_notes}")
            print(f"DEBUG: instructions = {response.instructions}")
            
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
                    print(f"DEBUG: Updated personality notes (deduplicated)")
                else:
                    print(f"DEBUG: Skipped duplicate personality note: {new_note[:50]}...")
            
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
                    print(f"DEBUG: Updated instructions (deduplicated)")
                else:
                    print(f"DEBUG: Skipped duplicate instruction: {new_instruction[:50]}...")
            
            if updated:
                # Use select_for_update to prevent concurrent modifications
                from django.db import transaction
                with transaction.atomic():
                    chat_history.save()
                    print("DEBUG: ChatHistory saved successfully")
                    
        except Exception as e:
            print(f"DEBUG: Error in update_memory: {e}")
            # Don't raise the exception to avoid breaking the main flow

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
                lines.append(f"- {t.course_code or t.course_name} at {t.time_slot} in {t.venue}")
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
            return f"Next class: {upcoming.course_code or upcoming.course_name} at {upcoming.time_slot} in {upcoming.venue}. [LINK:/app/timetable]"
        
        if qt == "assignments":
            return "You have no tracked assignments yet. Want me to set a reminder? [ACTION:set_reminder]"
        
        if qt == "autocad":
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

