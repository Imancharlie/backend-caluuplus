"""
Token/Economy subsystem for Caluu+.

This app owns the complete token lifecycle:
  - earning (rewards)
  - consuming (spending)
  - purchasing
  - transaction history / ledger
  - redemption of eligible EARNED tokens

Architectural rule: NO feature app should ever modify a token balance
directly. All token movement flows through tokens.services.token_service which
always writes an auditable TokenTransaction row and keeps the wallet in sync.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.utils import timezone


class TransactionType(models.TextChoices):
    """Machine-readable token transaction types."""
    PROFILE_COMPLETION = "PROFILE_COMPLETION", "Profile Completion"
    OPPORTUNITY_REWARD = "OPPORTUNITY_REWARD", "Opportunity Reward"
    ARTICLE_REWARD = "ARTICLE_REWARD", "Article Reward"
    ARTICLE_SHARE_REWARD = "ARTICLE_SHARE_REWARD", "Article Share Reward"
    SURVEY_REWARD = "SURVEY_REWARD", "Survey Reward"
    SURVEY_QUESTION_REWARD = "SURVEY_QUESTION_REWARD", "Survey Question Reward"
    REFERRAL_REWARD = "REFERRAL_REWARD", "Referral Reward"
    TOKEN_PURCHASE = "TOKEN_PURCHASE", "Token Purchase"
    GPA_CONSUMPTION = "GPA_CONSUMPTION", "GPA Consumption"
    MR_CALUU_CONSUMPTION = "MR_CALUU_CONSUMPTION", "Mr Caluu Consumption"
    MAP_CONSUMPTION = "MAP_CONSUMPTION", "Caluu Map Consumption"
    TOKEN_REDEMPTION = "TOKEN_REDEMPTION", "Token Redemption"
    REDEMPTION_RELEASE = "REDEMPTION_RELEASE", "Redemption Release"
    REFUND = "REFUND", "Refund"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT", "Admin Adjustment"


class TokenKind(models.TextChoices):
    EARNED = "earned", "Earned"
    PURCHASED = "purchased", "Purchased"


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class Stream(models.TextChoices):
    """Which ledgers a token movement touches."""
    EARNED = "earned", "Earned"
    PURCHASED = "purchased", "Purchased"
    EARNED_PURCHASED = "earned_purchased", "Earned + Purchased"


class TokenWallet(models.Model):
    """
    A user's token wallet.

    The wallet holds cached/mutable balances for fast reads, but the
    Transaction ledger (TokenTransaction) is the authoritative record of all
    movement. The cached values are only ever updated by the token service
    inside a database transaction alongside the ledger, never by feature apps.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="token_wallet",
        help_text="The user who owns this wallet",
    )

    earned_balance = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Current spendable EARNED token balance.",
    )
    purchased_balance = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Current spendable PURCHASED token balance.",
    )

    # Lifetime running totals (informational / audit).
    earned_lifetime = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Total EARNED tokens ever credited.",
    )
    earned_redeemed = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Total EARNED tokens that have left via redemption.",
    )
    purchased_lifetime = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Total PURCHASED tokens ever credited.",
    )
    spent_lifetime = models.DecimalField(
        max_digits=20, decimal_places=0, default=0,
        help_text="Total tokens ever consumed (both kinds).",
    )

    is_active = models.BooleanField(default=True, help_text="Whether the wallet can receive/send tokens.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - total {self.total_balance}"

    @property
    def total_balance(self):
        return (self.earned_balance or 0) + (self.purchased_balance or 0)

    @property
    def available_earned(self):
        """
        Earned tokens available for spending/redemption.

        Held (in-flight) redemptions are already removed from
        ``earned_balance`` when the request is created, so this equals the
        current earnable balance.
        """
        return self.earned_balance

    def sync_user_cache(self):
        """Keep the legacy cached field on the User model in sync."""
        try:
            User = settings.AUTH_USER_MODEL
            from django.apps import apps
            user_model = apps.get_model(User)
            user_model.objects.filter(pk=self.user_id).update(
                tokens_balance=self.total_balance
            )
        except Exception:  # noqa: BLE001 - best effort cache only
            pass


class TokenTransaction(models.Model):
    """
    Immutable, auditable ledger entry for every token movement.

    Every credit, debit, purchase, refund or adjustment creates exactly one
    row here. The `reference_key` is intentionally unique-per-user so retried
    or replayed operations are idempotent and cannot double-count.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="token_transactions",
        db_index=True,
    )
    wallet = models.ForeignKey(
        TokenWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )

    transaction_type = models.CharField(
        max_length=50, choices=TransactionType.choices
    )
    kind = models.CharField(max_length=20, choices=TokenKind.choices)

    # Signed amount: positive for credit, negative for debit.
    amount = models.DecimalField(max_digits=20, decimal_places=0)

    # Balance snapshot of the impacted stream AFTER this transaction.
    earned_balance_after = models.DecimalField(
        max_digits=20, decimal_places=0, default=0
    )
    purchased_balance_after = models.DecimalField(
        max_digits=20, decimal_places=0, default=0
    )

    status = models.CharField(
        max_length=20, choices=TransactionStatus.choices,
        default=TransactionStatus.COMPLETED,
    )
    description = models.TextField(blank=True, default="")

    # Related object / activity (generic).
    content_type = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)

    # Idempotency / replay protection.
    reference_key = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    # Who/what initiated it.
    initiated_by = models.CharField(max_length=64, blank=True, default="system",
                                    help_text="system, user, admin:<pk>")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="initiated_token_transactions",
        help_text="The admin/actor who performed the operation, if any.",
    )

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "reference_key"], name="uniq_tokentx_user_ref"
            )
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["transaction_type"]),
            models.Index(fields=["kind"]),
            models.Index(fields=["wallet"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.transaction_type} ({self.amount})"


class BaseRule(models.Model):
    """
    Shared configurable-rule base for reward and consumption rules.

    Values live here so economic constants are NOT scattered across feature
    apps; admins configure amounts in the backend/admin.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True, help_text="Stable machine key, e.g. PROFILE_COMPLETION")
    label = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.label} ({self.amount})"


class RewardRule(BaseRule):
    """Configurable reward amounts per earning action."""
    class Meta:
        verbose_name = "Reward Rule"
        verbose_name_plural = "Reward Rules"


class ConsumptionRule(BaseRule):
    """Configurable token cost per consuming action."""
    class Meta:
        verbose_name = "Consumption Rule"
        verbose_name_plural = "Consumption Rules"


class TokenPackage(models.Model):
    """Available token purchase packages for the storefront."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    token_amount = models.DecimalField(max_digits=20, decimal_places=0,
                                       help_text="Number of tokens delivered")
    price_amount = models.DecimalField(max_digits=12, decimal_places=2,
                                       help_text="Price in configured currency")
    currency = models.CharField(max_length=3, default="TSH")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "token_amount"]
        indexes = [models.Index(fields=["is_active", "sort_order"])]

    def __str__(self):
        return f"{self.name} - {self.token_amount} tokens"


class TokenEconomyConfig(models.Model):
    """Global economic configuration (redemption limits, etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class Referral(models.Model):
    """
    A referral from `referrer` that brought in `referred`.

    A referral only becomes eligible for a reward when the referred user
    reaches the minimum verified state (configured via RewardRule
    'REFERRAL_REQUIRED_STATE' or the default: registered + phone verified +
    profile complete).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="issued_referrals",
        help_text="The user who referred someone.",
    )
    referred = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="incoming_referral",
        help_text="The referred (new) user.",
    )
    code = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=[
        ("pending", "Pending"),
        ("eligible", "Eligible"),
        ("rewarded", "Rewarded"),
        ("rejected", "Rejected"),
    ], default="pending")
    reward_transaction = models.ForeignKey(
        TokenTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["referrer"]), models.Index(fields=["code"])]

    def __str__(self):
        return f"{self.referrer} -> {self.referred} ({self.status})"


class ReferralCode(models.Model):
    """Unique referral code a user can share."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_code"
    )
    code = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.code}"


class RedemptionRequest(models.Model):
    """
    Controlled redemption of EARNED tokens.

    A redemption only ever draws from eligible EARNED tokens. Purchased
    tokens can never be redeemed. When a request is created, the earned
    balance is reserved (held) so the same tokens cannot be double-redeemed or
    re-spent; the deduction is only finalised once the request is approved and
    completed.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(TokenWallet, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="token_redemptions")

    # Amount of EARNED tokens requested.
    earned_amount = models.DecimalField(max_digits=20, decimal_places=0)

    # Payout target (provider abstraction).
    payout_provider = models.CharField(max_length=50, blank=True, default="manual")
    payout_target = models.CharField(max_length=255, blank=True, default="",
                                     help_text="e.g. phone number / account identifier")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    admin_note = models.TextField(blank=True, default="")
    review_reason = models.TextField(blank=True, default="")

    # Ledger linkage.
    hold_transaction = models.ForeignKey(
        TokenTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="holding_redemption", help_text="Reservation/hold ledger entry.",
    )
    finalize_transaction = models.ForeignKey(
        TokenTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finalized_redemption", help_text="Final deduction ledger entry.",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_redemptions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.user} - {self.earned_amount} earned ({self.status})"
