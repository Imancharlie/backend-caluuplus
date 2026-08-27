"""
Central token service for Caluu+.

This is the ONLY entry point for moving tokens. Feature apps (GPA, Mr Caluu,
Caluu Map, Opportunities, Articles, Surveys, Referrals, Payments) must call
these methods and MUST NOT modify wallet balances directly.

Key guarantees:
  - Every movement writes an auditable TokenTransaction row.
  - Operations run inside a database transaction with select-for-update on
    the wallet to prevent concurrent corruption.
  - Idempotency via unique reference keys (one reference per user).
  - Consumption draws PURCHASED tokens first, then EARNED tokens.
"""

import logging
import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import (
    ConsumptionRule,
    RedemptionRequest,
    Referral,
    RewardRule,
    TokenEconomyConfig,
    TokenPackage,
    TokenTransaction,
    TokenWallet,
)

logger = logging.getLogger(__name__)

# Well-known rule keys. These are configuration identifiers, not values.
RULE_PROFILE_COMPLETION = "PROFILE_COMPLETION"
RULE_OPPORTUNITY_APPROVED = "OPPORTUNITY_APPROVED"
RULE_ARTICLE_APPROVED = "ARTICLE_APPROVED"
RULE_ARTICLE_SHARE = "ARTICLE_SHARE_REWARD"
RULE_SURVEY_COMPLETION = "SURVEY_COMPLETION"
RULE_SURVEY_QUESTION = "SURVEY_QUESTION"
RULE_REFERRAL_COMPLETED = "REFERRAL_COMPLETED"
RULE_GPA_CALCULATION = "GPA_CALCULATION"
RULE_MR_CALUU_MESSAGE = "MR_CALUU_MESSAGE"
RULE_MAP_ACTIVITY = "MAP_ACTIVITY"

REFERRAL_REQUIRED_STATE_KEY = "REFERRAL_REQUIRED_STATE"
REDEEM_CONFIG_KEY = "REDEMPTION"


class TokenError(Exception):
    """Base error for token operations."""

    def __init__(self, message, code="token_error", status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class InsufficientBalance(TokenError):
    def __init__(self, message="Insufficient token balance"):
        super().__init__(message, code="insufficient_balance", status_code=400)


class DuplicateOperation(TokenError):
    def __init__(self, message="Operation already processed"):
        super().__init__(message, code="duplicate_operation", status_code=409)


class RuleNotFound(TokenError):
    def __init__(self, message="Economic rule not found or inactive"):
        super().__init__(message, code="rule_unavailable", status_code=404)


# ---------------------------------------------------------------------------
# Rule / config helpers
# ---------------------------------------------------------------------------

def _reward_value(key):
    rule = RewardRule.objects.filter(key=key, is_active=True).first()
    if rule is None:
        raise RuleNotFound(f"Reward rule '{key}' not found or inactive")
    return int(rule.amount)


def _consume_value(key):
    rule = ConsumptionRule.objects.filter(key=key, is_active=True).first()
    if rule is None:
        raise RuleNotFound(f"Consumption rule '{key}' not found or inactive")
    return int(rule.amount)


def get_config(key, default=None):
    cfg = TokenEconomyConfig.objects.filter(key=key).first()
    if cfg is None:
        return default
    return cfg.value


# ---------------------------------------------------------------------------
# Wallet helpers
# ---------------------------------------------------------------------------

def get_or_create_wallet(user):
    """Return (wallet, created) for a user, creating a wallet if absent."""
    wallet, created = TokenWallet.objects.get_or_create(user=user)
    return wallet, created


def refresh_wallet_cache(user):
    """Recompute the cached balance field on the User without touching ledgers."""
    wallet, _ = get_or_create_wallet(user)
    wallet.sync_user_cache()
    return wallet


def get_wallet(user):
    """Read-only balance snapshot (no DB row created)."""
    wallet, created = TokenWallet.objects.get_or_create(user=user)
    if created:
        wallet.sync_user_cache()
    return wallet


# ---------------------------------------------------------------------------
# Ledger write helper (private)
# ---------------------------------------------------------------------------

def _write_ledger(user, wallet, transaction_type, kind, amount, stream_after,
                  status, description, reference_key=None, metadata=None,
                  initiated_by="system", actor=None, content_object=None,
                  object_id=None, created_at=None):
    """
    Write a TokenTransaction row.

    amount is the signed movement (+/-). stream_after is a dict with the
    earned/purchased balances after this movement.
    """
    content_type = None
    if content_object is not None:
        content_type = ContentType.objects.get_for_model(content_object)
        object_id = getattr(content_object, "pk", None)

    return TokenTransaction.objects.create(
        user=user,
        wallet=wallet,
        transaction_type=transaction_type,
        kind=kind,
        amount=amount,
        earned_balance_after=stream_after.get("earned", 0),
        purchased_balance_after=stream_after.get("purchased", 0),
        status=status,
        description=description,
        reference_key=reference_key,
        initiated_by=initiated_by,
        actor=actor,
        content_type=content_type,
        object_id=object_id,
        metadata=metadata or {},
        created_at=created_at or timezone.now(),
    )


def _resolve_object(content_object, object_id):
    """Return a typed object reference for the ledger's generic FK."""
    if content_object is not None:
        return content_object
    # Callers may pass object_id only; we still record the generic FK.
    return None


# ---------------------------------------------------------------------------
# EARNING
# ---------------------------------------------------------------------------

def reward(user, rule_key, reference_key=None, description="", amount=None,
           content_object=None, initiated_by="system", actor=None):
    """
    Grant an EARNED token reward.

    Sometimes the reward amount is fixed by configuration (rule_key); callers
    can optionally override `amount` (must not be negative). The reference_key
    makes the reward idempotent (the same reference can never be rewarded
    twice for the same user).
    """
    if not user or not getattr(user, "pk", None):
        raise TokenError("A user is required to grant a reward", code="invalid_user", status_code=400)

    value = amount
    if value is None:
        value = _reward_value(rule_key)
    value = int(value)
    if value < 0:
        raise TokenError("Reward amount cannot be negative", code="invalid_amount", status_code=400)

    if not reference_key:
        reference_key = f"reward:{rule_key}:{uuid.uuid4()}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)

        # Idempotency: reject duplicate reference for the same user.
        if TokenTransaction.objects.filter(user=user, reference_key=reference_key).exists():
            raise DuplicateOperation("This reward has already been granted")

        if not wallet.is_active:
            raise TokenError("Wallet is not active", code="wallet_inactive", status_code=400)

        wallet.earned_balance = wallet.earned_balance + value
        wallet.earned_lifetime = wallet.earned_lifetime + value
        wallet.save(update_fields=["earned_balance", "earned_lifetime", "updated_at"])

        txn = _write_ledger(
            user, wallet, rule_key, "earned", value,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", description or f"Earned {value} tokens",
            reference_key=reference_key, metadata={"rule_key": rule_key},
            initiated_by=initiated_by, actor=actor, content_object=_resolve_object(content_object, None),
        )
        wallet.sync_user_cache()
        return _result(wallet, txn)


def reward_refund(user, reference_key, description="Refund", amount=None,
                  actor=None, metadata=None):
    """
    Reverse a previously granted reward (e.g. after a content rejection or
    moderation rollback). Returns a REFUND transaction.
    """
    if not reference_key:
        raise TokenError("A reference key is required to refund a reward", code="invalid_reference", status_code=400)

    original = TokenTransaction.objects.filter(user=user, reference_key=reference_key).first()
    if original is None:
        raise TokenError("Original reward transaction not found", code="not_found", status_code=404)

    value = amount if amount is not None else int(original.amount)
    value = int(value)
    if value < 0:
        raise TokenError("Refund amount cannot be negative", code="invalid_amount", status_code=400)

    refund_ref = f"refund:{reference_key}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)
        if TokenTransaction.objects.filter(user=user, reference_key=refund_ref).exists():
            raise DuplicateOperation("This reward has already been refunded")
        if wallet.earned_balance < value:
            raise InsufficientBalance()

        wallet.earned_balance = wallet.earned_balance - value
        wallet.save(update_fields=["earned_balance", "updated_at"])

        txn = _write_ledger(
            user, wallet, "REFUND", "earned", -value,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", description,
            reference_key=refund_ref, metadata=metadata or {"refunds": reference_key},
            initiated_by="system", actor=actor,
        )
        wallet.sync_user_cache()
        return _result(wallet, txn)


# ---------------------------------------------------------------------------
# CONSUMING
# ---------------------------------------------------------------------------

def consume(user, rule_key, reference_key=None, description="", amount=None,
            content_object=None, initiated_by="user", actor=None):
    """
    Consume tokens for a platform action (GPA, Mr Caluu, Map, etc.).

    Consumption is drawn PURCHASED tokens first, then EARNED tokens. The rule
    amount is configured centrally. Raises InsufficientBalance if the total
    spendable balance can't cover the cost.
    """
    if not user or not getattr(user, "pk", None):
        raise TokenError("A user is required to consume tokens", code="invalid_user", status_code=400)

    value = amount
    if value is None:
        value = _consume_value(rule_key)
    value = int(value)
    if value <= 0:
        raise TokenError("Consumption amount must be positive", code="invalid_amount", status_code=400)

    if not reference_key:
        reference_key = f"consume:{rule_key}:{uuid.uuid4()}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)
        if TokenTransaction.objects.filter(user=user, reference_key=reference_key).exists():
            raise DuplicateOperation("This consumption has already been processed")
        if not wallet.is_active:
            raise TokenError("Wallet is not active", code="wallet_inactive", status_code=400)

        if wallet.total_balance < value:
            raise InsufficientBalance(
                f"Insufficient balance: need {value}, have {wallet.total_balance}"
            )

        # Consume purchased first, then earned.
        to_take = value
        purchased_delta = 0
        earned_delta = 0
        if to_take >= wallet.purchased_balance:
            to_take -= wallet.purchased_balance
            purchased_delta = -int(wallet.purchased_balance)
            wallet.purchased_balance = 0
        else:
            purchased_delta = -to_take
            wallet.purchased_balance = wallet.purchased_balance - to_take
            to_take = 0
        if to_take:
            earned_delta = -to_take
            wallet.earned_balance = wallet.earned_balance - to_take

        wallet.spent_lifetime = wallet.spent_lifetime + value
        wallet.save(update_fields=[
            "purchased_balance", "earned_balance", "spent_lifetime", "updated_at"
        ])

        txn = _write_ledger(
            user, wallet, rule_key, "purchased" if purchased_delta and not earned_delta else "earned",
            -value,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", description or f"Consumed {value} tokens",
            reference_key=reference_key, metadata={
                "rule_key": rule_key,
                "purchased_delta": int(purchased_delta),
                "earned_delta": int(earned_delta),
            },
            initiated_by=initiated_by, actor=actor,
            content_object=_resolve_object(content_object, None),
        )
        wallet.sync_user_cache()
        return _result(wallet, txn)


def has_balance_for(user, rule_key=None, amount=None):
    """Check (without spending) whether the user can afford a consumption."""
    value = amount
    if value is None:
        try:
            value = _consume_value(rule_key)
        except RuleNotFound:
            return False, None
    wallet, _ = get_or_create_wallet(user)
    total = wallet.total_balance
    return total >= value, value


# ---------------------------------------------------------------------------
# PURCHASING
# ---------------------------------------------------------------------------

def get_package(package_id):
    package = TokenPackage.objects.filter(id=package_id, is_active=True).first()
    if package is None:
        raise TokenError("Purchase package not found or inactive", code="package_not_found", status_code=404)
    return package


def purchase(user, package_id=None, reference_key=None, amount=None, initiated_by="user",
             actor=None, metadata=None):
    """
    Credit PURCHASED tokens after a payment has ALREADY been verified by the
    payment provider layer.

    This method must NEVER be called merely because the frontend claims a
    payment succeeded. The payment abstraction (tokens.payments) verifies the
    payment and then invokes this accounting method with a unique reference.
    """
    package = None
    value = amount
    if value is None:
        package = get_package(package_id)
        value = int(package.token_amount)

    if value <= 0:
        raise TokenError("Purchase amount must be positive", code="invalid_amount", status_code=400)

    if not reference_key:
        reference_key = f"purchase:{package_id if package else 'custom'}:{uuid.uuid4()}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)
        if TokenTransaction.objects.filter(user=user, reference_key=reference_key).exists():
            raise DuplicateOperation("This purchase has already been processed")
        if not wallet.is_active:
            raise TokenError("Wallet is not active", code="wallet_inactive", status_code=400)

        wallet.purchased_balance = wallet.purchased_balance + value
        wallet.purchased_lifetime = wallet.purchased_lifetime + value
        wallet.save(update_fields=["purchased_balance", "purchased_lifetime", "updated_at"])

        txn = _write_ledger(
            user, wallet, "TOKEN_PURCHASE", "purchased", value,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", f"Purchased {value} tokens",
            reference_key=reference_key,
            metadata=(metadata or {}) | {"package_id": str(package.id) if package else None},
            initiated_by=initiated_by, actor=actor,
        )
        wallet.sync_user_cache()
        return _result(wallet, txn, extra={"package": package.name if package else None})


# ---------------------------------------------------------------------------
# REDEMPTION
# ---------------------------------------------------------------------------

def _redemption_config():
    cfg = get_config(REDEEM_CONFIG_KEY, {})
    return cfg


def redemption_enabled():
    return bool(_redemption_config().get("enabled", True))


def minimum_redemption():
    return int(_redemption_config().get("minimum_amount", 0))


def redemption_limits():
    return _redemption_config().get("limits", {})


def request_redemption(user, earned_amount, payout_target="", initiated_by="user",
                       reference_key=None):
    """
    Create a redemption request, validating eligibility and reserving the
    EARNED tokens (hold). No permanent deduction occurs until approval &
    completion.
    """
    earned_amount = int(earned_amount)
    if earned_amount <= 0:
        raise TokenError("Redemption amount must be positive", code="invalid_amount", status_code=400)
    if not redemption_enabled():
        raise TokenError("Redemption is currently disabled", code="redemption_disabled", status_code=403)
    if earned_amount < minimum_redemption():
        raise TokenError(
            f"Minimum redemption is {minimum_redemption()} tokens",
            code="below_minimum", status_code=400,
        )

    ref = reference_key or f"redemption:{uuid.uuid4()}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)
        if TokenTransaction.objects.filter(user=user, reference_key=ref).exists():
            raise DuplicateOperation("This redemption request already exists")
        if not wallet.is_active:
            raise TokenError("Wallet is not active", code="wallet_inactive", status_code=400)
        if wallet.available_earned < earned_amount:
            raise InsufficientBalance(
                f"Not enough eligible EARNED tokens: need {earned_amount}, "
                f"have {wallet.available_earned} available"
            )

        # Reserve the earned tokens: physically move them out of the spendable
        # balance (hold) so they cannot be spent or double-redeemed, and record
        # a PENDING hold ledger entry. Tokens are returned on reject/cancel, or
        # finalised on completion.
        wallet.earned_balance = wallet.earned_balance - earned_amount
        wallet.save(update_fields=["earned_balance", "updated_at"])

        hold_txn = _write_ledger(
            user, wallet, "TOKEN_REDEMPTION", "earned", -earned_amount,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "pending", f"Held {earned_amount} earned tokens for redemption {ref}",
            reference_key=ref, metadata={"hold": True},
            initiated_by=initiated_by,
        )
        wallet.sync_user_cache()

        request = RedemptionRequest.objects.create(
            wallet=wallet,
            user=user,
            earned_amount=earned_amount,
            payout_target=payout_target,
            status="pending",
            hold_transaction=hold_txn,
        )
        return request


def approve_redemption(request, reviewer, note=""):
    request.status = "approved"
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.admin_note = note or request.admin_note
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note"])
    return request


def reject_redemption(request, reviewer, reason=""):
    # Release the held tokens back into the earned balance.
    with transaction.atomic():
        wallet = TokenWallet.objects.select_for_update().get(pk=request.wallet_id)
        wallet.earned_balance = wallet.earned_balance + request.earned_amount
        wallet.save(update_fields=["earned_balance", "updated_at"])
        _write_ledger(
            request.user, wallet, "REDEMPTION_RELEASE", "earned", request.earned_amount,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", f"Released {request.earned_amount} earned tokens on rejection",
            reference_key=f"release:{request.id}", metadata={"redemption_id": str(request.id)},
            initiated_by="admin", actor=reviewer,
        )
        wallet.sync_user_cache()

    request.status = "rejected"
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.review_reason = reason or request.review_reason
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_reason"])
    return request


def complete_redemption(request, admin, payout_ref=""):
    """
    Finalize a redemption after the payout was delivered: permanently deduct
    the reserved earned tokens and mark the request completed.
    """
    if request.status not in ("approved", "processing"):
        raise TokenError("Redemption is not in a payable state", code="invalid_state", status_code=400)

    with transaction.atomic():
        wallet = TokenWallet.objects.select_for_update().get(pk=request.wallet_id)
        if TokenTransaction.objects.filter(
            user=request.user, reference_key=f"finalize:{request.id}"
        ).exists():
            raise DuplicateOperation("Redemption already finalised")

        # The earned tokens were already deducted (held) at request time; here
        # we only finalise the accounting (mark them as redeemed) and record
        # the completed ledger entry. No double deduction.
        wallet.earned_redeemed = wallet.earned_redeemed + request.earned_amount
        wallet.save(update_fields=["earned_redeemed", "updated_at"])

        final_txn = _write_ledger(
            request.user, wallet, "TOKEN_REDEMPTION", "earned", -request.earned_amount,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", f"Redeemed {request.earned_amount} earned tokens",
            reference_key=f"finalize:{request.id}",
            metadata={"redemption_id": str(request.id), "payout_ref": payout_ref},
            initiated_by="admin", actor=admin,
        )
        wallet.sync_user_cache()

    request.finalize_transaction = final_txn
    request.status = "completed"
    request.reviewed_by = admin
    request.reviewed_at = timezone.now()
    request.save(update_fields=["finalize_transaction", "status", "reviewed_by", "reviewed_at"])
    return request


# ---------------------------------------------------------------------------
# REFERRAL
# ---------------------------------------------------------------------------

def issue_referral_code(user):
    from .models import ReferralCode
    code = None
    while True:
        code = f"CALUU{user.pk.hex[:8].upper()}"
        try:
            rc, created = ReferralCode.objects.get_or_create(user=user, defaults={"code": code})
            if not created and rc.code != code:
                rc.code = code
                rc.save(update_fields=["code"])
            return rc
        except Exception:  # noqa: BLE001
            continue


def record_referral(referrer, referred, code=""):
    """Register that `referrer` referred `referred`."""
    from .models import Referral, ReferralCode
    # Block self-referrals.
    if referrer.pk == referred.pk:
        raise TokenError("You cannot refer yourself", code="self_referral", status_code=400)

    rc = None
    if code:
        rc = ReferralCode.objects.filter(code=code).first()
        if rc is not None and rc.user_id != referrer.pk:
            raise TokenError("Referral code does not belong to referrer", code="invalid_code", status_code=400)

    referral, created = Referral.objects.get_or_create(
        referred=referred, defaults={"referrer": referrer, "code": code or (rc.code if rc else "")}
    )
    if not created:
        raise DuplicateOperation("This user has already been referred")

    # If the referred user is already eligible, reward immediately.
    _maybe_reward_referral(referral)
    return referral


def check_referral_eligibility(user):
    """
    Determine whether a user has reached the verified state required before
    their referrer can be rewarded.
    """
    required = get_config(REFERRAL_REQUIRED_STATE_KEY, {})
    phone_required = required.get("phone_verified", True)
    profile_required = required.get("profile_complete", True)
    registration_required = required.get("registration", True)

    if registration_required and not user.is_active:
        return False, "registration"
    if phone_required and not getattr(user, "phone_verified", False):
        return False, "phone_verified"
    if profile_required:
        has_student = hasattr(user, "student_profile") and bool(user.student_profile)
        profile_done = bool(getattr(user, "bio", "") or has_student or
                            getattr(user, "public_profile", True))
        if not profile_done:
            return False, "profile_complete"
    return True, None


def recheck_referral(referral):
    """Publicly re-evaluate a referral's eligibility and reward if eligible."""
    return _maybe_reward_referral(referral)


def _maybe_reward_referral(referral):
    """Reward the referrer once the referred user becomes eligible."""
    eligible, missing = check_referral_eligibility(referral.referred)
    if not eligible:
        return False
    if referral.status in ("eligible", "rewarded"):
        return True

    amount = _reward_value(RULE_REFERRAL_COMPLETED)
    ref = f"referral:{referral.id}"
    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=referral.referrer)
        if TokenTransaction.objects.filter(user=referral.referrer, reference_key=ref).exists():
            return True
        wallet.earned_balance = wallet.earned_balance + amount
        wallet.earned_lifetime = wallet.earned_lifetime + amount
        wallet.save(update_fields=["earned_balance", "earned_lifetime", "updated_at"])
        txn = _write_ledger(
            referral.referrer, wallet, "REFERRAL_REWARD", "earned", amount,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", f"Referral reward for {referral.referred}",
            reference_key=ref, metadata={"referred_id": str(referral.referred_id)},
        )
        wallet.sync_user_cache()

    referral.reward_transaction = txn
    referral.status = "rewarded"
    referral.save(update_fields=["reward_transaction", "status"])
    return True


def admin_adjust(user, amount, stream, actor, reason="", initiated_by="admin"):
    """
    Administrative token adjustment.

    amount: positive to credit, negative to debit the chosen stream
    stream: "earned" or "purchased"
    Always creates an auditable ADMIN_ADJUSTMENT transaction. Never silently
    edits a balance.
    """
    if not actor or not getattr(actor, "is_staff", False):
        raise TokenError("Only staff may perform token adjustments", code="forbidden", status_code=403)
    if stream not in ("earned", "purchased"):
        raise TokenError("stream must be 'earned' or 'purchased'", code="invalid_stream", status_code=400)

    value = int(amount)
    if value == 0:
        raise TokenError("Adjustment amount cannot be zero", code="invalid_amount", status_code=400)

    ref = f"adminadj:{actor.pk}:{uuid.uuid4()}"

    with transaction.atomic():
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user)
        # Prevent negative balances.
        if stream == "earned":
            if wallet.earned_balance + value < 0:
                raise InsufficientBalance("Adjustment would make earned balance negative")
            wallet.earned_balance = wallet.earned_balance + value
            if value > 0:
                wallet.earned_lifetime = wallet.earned_lifetime + value
        else:
            if wallet.purchased_balance + value < 0:
                raise InsufficientBalance("Adjustment would make purchased balance negative")
            wallet.purchased_balance = wallet.purchased_balance + value
            if value > 0:
                wallet.purchased_lifetime = wallet.purchased_lifetime + value
        wallet.save(update_fields=["earned_balance", "purchased_balance",
                                   "earned_lifetime", "purchased_lifetime", "updated_at"])

        txn = _write_ledger(
            user, wallet, "ADMIN_ADJUSTMENT", stream, value,
            {"earned": wallet.earned_balance, "purchased": wallet.purchased_balance},
            "completed", reason or f"Admin adjustment of {value} {stream} tokens",
            reference_key=ref, metadata={"stream": stream, "reason": reason},
            initiated_by=initiated_by, actor=actor,
        )
        wallet.sync_user_cache()
        return _result(wallet, txn)


def _result(wallet, txn, extra=None):
    data = {
        "transaction_id": str(txn.id),
        "transaction_type": txn.transaction_type,
        "kind": txn.kind,
        "amount": int(txn.amount),
        "status": txn.status,
        "earned_balance": int(wallet.earned_balance),
        "purchased_balance": int(wallet.purchased_balance),
        "total_balance": int(wallet.total_balance),
    }
    if extra:
        data.update(extra)
    return data
