from rest_framework import serializers
from .models import Conversation, Message, ChatHistory, KnowledgeSuggestion


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "tokens_used", "input_tokens", "output_tokens", "cost_tsh", "timestamp", "topic"]
        read_only_fields = ["id", "tokens_used", "input_tokens", "output_tokens", "cost_tsh", "timestamp", "topic"]


class ConversationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "title", "is_active", "created_at", "updated_at", "total_tokens", "total_input_tokens", "total_output_tokens", "total_cost_tsh"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "is_active", "created_at", "updated_at", "total_tokens", "total_input_tokens", "total_output_tokens", "total_cost_tsh", "messages"]
        read_only_fields = ["id", "created_at", "updated_at", "total_tokens", "total_input_tokens", "total_output_tokens", "total_cost_tsh", "messages"]


class ChatHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatHistory
        fields = ["id", "user", "personality_notes", "instructions", "last_updated"]
        read_only_fields = ["id", "user", "last_updated"]


class KnowledgeSuggestionSerializer(serializers.ModelSerializer):
    user_display = serializers.CharField(source='user.display_name', read_only=True)
    reviewed_by_display = serializers.CharField(source='reviewed_by.display_name', read_only=True)

    class Meta:
        model = KnowledgeSuggestion
        fields = [
            'id', 'query_text', 'response_text', 'trigger',
            'confidence_score', 'status', 'created_at',
            'occurrence_count', 'last_seen_at',
            'user', 'user_display', 'reviewed_by', 'reviewed_by_display', 'reviewed_at'
        ]
        read_only_fields = ['id', 'query_hash', 'created_at', 'reviewed_at',
                            'occurrence_count', 'last_seen_at']
