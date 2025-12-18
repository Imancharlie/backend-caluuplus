from rest_framework import serializers
from .models import Conversation, Message, ChatHistory


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
