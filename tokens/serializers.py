from rest_framework import serializers

from .models import (
    ConsumptionRule,
    RedemptionRequest,
    Referral,
    RewardRule,
    TokenPackage,
    TokenTransaction,
    TokenWallet,
)


class TokenRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardRule
        fields = ["id", "key", "label", "amount", "is_active", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TokenWalletSerializer(serializers.ModelSerializer):
    total_balance = serializers.IntegerField(read_only=True)
    available_earned = serializers.IntegerField(read_only=True)

    class Meta:
        model = TokenWallet
        fields = [
            "earned_balance",
            "purchased_balance",
            "total_balance",
            "available_earned",
            "earned_lifetime",
            "earned_redeemed",
            "purchased_lifetime",
            "spent_lifetime",
            "is_active",
            "created_at",
            "updated_at",
        ]


class TokenTransactionSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = TokenTransaction
        fields = [
            "id",
            "user",
            "transaction_type",
            "kind",
            "amount",
            "status",
            "description",
            "earned_balance_after",
            "purchased_balance_after",
            "reference_key",
            "initiated_by",
            "created_at",
        ]


class TokenPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenPackage
        fields = [
            "id",
            "name",
            "token_amount",
            "price_amount",
            "currency",
            "is_active",
            "sort_order",
            "description",
        ]


class RedemptionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedemptionRequest
        fields = [
            "id",
            "earned_amount",
            "payout_target",
            "payout_provider",
            "status",
            "admin_note",
            "review_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "admin_note", "review_reason", "created_at", "updated_at"]


class AdminRedemptionRequestSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user_id", read_only=True)
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = RedemptionRequest
        fields = [
            "id",
            "user_id",
            "user_name",
            "user_email",
            "user_phone",
            "earned_amount",
            "payout_target",
            "payout_provider",
            "status",
            "admin_note",
            "review_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
