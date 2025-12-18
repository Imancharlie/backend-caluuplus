from django.conf import settings
from django.db import models
import uuid


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_conversations")
    title = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_input_tokens = models.IntegerField(default=0)
    total_output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    total_cost_tsh = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    summary = models.TextField(blank=True, null=True, help_text="Rolling summary of conversation for memory")

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversation {self.id}"


class Message(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.IntegerField(default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost_tsh = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    # Optional topic tag for this message
    topic = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"


class ChatHistory(models.Model):
    """Stores persistent user preferences and personality notes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_history')
    
    # Personalization fields
    personality_notes = models.TextField(
        blank=True, 
        null=True,
        help_text="Info about user: friends, interests, habits, etc."
    )
    instructions = models.TextField(
        blank=True, 
        null=True,
        help_text="User preferences: 'speak Kiswahili', 'call me bro', etc."
    )
    
    # Metadata
    total_conversations = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    total_cost_tsh = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.display_name} - Chat History"

    def update_stats(self, tokens: int, cost_tsh):
        """Update aggregated usage stats for this user."""
        from decimal import Decimal
        self.total_messages += 1
        self.total_tokens += int(tokens or 0)
        self.total_cost_tsh = (self.total_cost_tsh or 0) + Decimal(str(cost_tsh or 0))
        self.save(update_fields=["total_messages", "total_tokens", "total_cost_tsh"])


class KnowledgeDocument(models.Model):
    """Store domain-specific documents for RAG"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=[
            ('faq', 'FAQ'),
            ('policy', 'Policy'),
            ('guide', 'Guide'),
            ('schedule', 'Schedule Info'),
            ('regulation', 'Regulation'),
            ('procedure', 'Procedure'),
            ('calendar', 'Calendar Event'),
            ('navigation', 'Navigation'),
            ('academic_advice', 'Academic Advice'),
            ('program_info', 'Program Information'),
        ],
        default='faq'
    )
    university = models.ForeignKey('api.University', on_delete=models.CASCADE, null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags for better searchability")
    priority = models.IntegerField(default=5, help_text="Priority score 1-10 (higher = more important)")
    usage_count = models.IntegerField(default=0, help_text="Number of times this document has been retrieved")
    is_active = models.BooleanField(default=True, help_text="Whether this document is active and searchable")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', '-usage_count', '-created_at']
        indexes = [
            models.Index(fields=['category', 'university', 'is_active']),
            models.Index(fields=['priority', 'usage_count']),
        ]
    
    def __str__(self):
        return self.title
    
    def increment_usage(self):
        """Increment usage count when document is retrieved"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])
    
    def get_tags_list(self):
        """Return tags as a list"""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]


class SiteNavigation(models.Model):
    """Store Caluu+ site navigation and feature information"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Feature or page name")
    route = models.CharField(max_length=200, help_text="Route path (e.g., /app/timetable)")
    description = models.TextField(help_text="Description of what this feature does")
    keywords = models.CharField(max_length=500, blank=True, help_text="Comma-separated keywords for search")
    icon = models.CharField(max_length=100, blank=True, help_text="Icon name or identifier")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['route', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.route})"
    
    def get_keywords_list(self):
        """Return keywords as a list"""
        if not self.keywords:
            return []
        return [kw.strip() for kw in self.keywords.split(',') if kw.strip()]


class Feedback(models.Model):
    """Track user feedback on chatbot responses"""
    RATING_CHOICES = [
        (1, 'Very Poor'),
        (2, 'Poor'),
        (3, 'Neutral'),
        (4, 'Good'),
        (5, 'Excellent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chatbot_feedback')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='feedback', null=True, blank=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='feedback', null=True, blank=True)
    rating = models.IntegerField(choices=RATING_CHOICES, help_text="User rating of the response")
    comment = models.TextField(blank=True, help_text="Optional user comment")
    query = models.TextField(help_text="Original user query")
    response = models.TextField(help_text="Chatbot response that was rated")
    knowledge_documents_used = models.ManyToManyField(KnowledgeDocument, blank=True, help_text="Knowledge documents used in this response")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'rating', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.display_name} - {self.rating}/5 - {self.created_at.date()}"


class ConversationAnalytics(models.Model):
    """Analytics and insights from conversations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name='analytics')
    
    # Query analysis
    query_intent = models.CharField(max_length=100, blank=True, help_text="Detected intent of queries")
    common_topics = models.JSONField(default=list, help_text="List of common topics discussed")
    knowledge_gaps = models.JSONField(default=list, help_text="Queries that couldn't be answered well")
    
    # Performance metrics
    avg_response_time = models.FloatField(default=0.0, help_text="Average response time in seconds")
    total_api_calls = models.IntegerField(default=0)
    total_cache_hits = models.IntegerField(default=0)
    
    # User satisfaction
    avg_rating = models.FloatField(default=0.0, help_text="Average feedback rating")
    feedback_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Analytics for {self.conversation.title}"
    
    def update_metrics(self, response_time=None, api_call=False, cache_hit=False, rating=None):
        """Update analytics metrics"""
        if response_time is not None:
            # Calculate running average
            total_messages = self.conversation.messages.count()
            if total_messages > 0:
                self.avg_response_time = ((self.avg_response_time * (total_messages - 1)) + response_time) / total_messages
        
        if api_call:
            self.total_api_calls += 1
        if cache_hit:
            self.total_cache_hits += 1
        if rating is not None:
            # Update average rating
            self.feedback_count += 1
            self.avg_rating = ((self.avg_rating * (self.feedback_count - 1)) + rating) / self.feedback_count
        
        self.save()


