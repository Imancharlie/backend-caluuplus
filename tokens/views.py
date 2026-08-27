from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services as token_service
from . import services
from .models import (
    RedemptionRequest,
    Referral,
    ReferralCode,
    RewardRule,
    TokenPackage,
    TokenTransaction,
    TokenWallet,
)
from .serializers import (
    RedemptionRequestSerializer,
    TokenPackageSerializer,
    TokenTransactionSerializer,
    TokenWalletSerializer,
)


class TokensPermission(permissions.IsAuthenticated):
    """Tokens endpoints require an authenticated user."""


class StandardPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


def _error(exc):
    return Response(
        {"error": exc.message, "code": exc.code},
        status=exc.status_code or status.HTTP_400_BAD_REQUEST,
    )


# ---------------------------------------------------------------------------
# Wallet & ledger
# ---------------------------------------------------------------------------

class WalletView(APIView):
    """
    GET /api/tokens/wallet/
    Returns the current wallet balance (earned, purchased, total).
    """
    permission_classes = [TokensPermission]

    @extend_schema(responses=TokenWalletSerializer)
    def get(self, request):
        wallet = token_service.get_wallet(request.user)
        return Response(TokenWalletSerializer(wallet).data)


class WalletHistoryView(APIView):
    """
    GET /api/tokens/history/?type=&kind=&page=
    Paginated token transaction history for the current user.
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        qs = TokenTransaction.objects.filter(user=request.user).select_related("user")
        t_type = request.query_params.get("type")
        kind = request.query_params.get("kind")
        if t_type:
            qs = qs.filter(transaction_type=t_type)
        if kind:
            qs = qs.filter(kind=kind)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            TokenTransactionSerializer(page if page is not None else qs, many=True).data
        )


class TransactionDetailView(APIView):
    """
    GET /api/tokens/history/{id}/
    Detail of a single transaction.
    """
    permission_classes = [TokensPermission]

    def get(self, request, pk):
        txn = TokenTransaction.objects.filter(user=request.user, pk=pk).first()
        if txn is None:
            return Response({"error": "Transaction not found", "code": "not_found"},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(TokenTransactionSerializer(txn).data)


class AvailableRewardsView(APIView):
    """
    GET /api/tokens/rewards/
    Lists active earning opportunities (reward rules) for the frontend.
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        rules = RewardRule.objects.filter(is_active=True).order_by("key")
        data = [
            {"key": r.key, "label": r.label, "amount": int(r.amount), "description": r.description}
            for r in rules
        ]
        return Response({"rewards": data})


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------

class ConsumeView(APIView):
    """
    POST /api/tokens/consume/
    Body: {"rule_key": "GPA_CALCULATION", "reference_key": "...", "description": "..."}

    Consumes tokens (purchased first, then earned) using the centrally
    configured rule. The amount is never taken from the client.
    """
    permission_classes = [TokensPermission]

    def post(self, request):
        rule_key = request.data.get("rule_key")
        reference_key = request.data.get("reference_key")
        description = request.data.get("description", "")
        if not rule_key:
            return Response({"error": "rule_key is required", "code": "missing_rule"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            result = token_service.consume(
                request.user, rule_key, reference_key=reference_key or None, description=description
            )
        except services.TokenError as exc:
            return _error(exc)
        return Response(result, status=status.HTTP_200_OK)


class SurveyRewardView(APIView):
    """
    POST /api/tokens/survey-reward/
    Body: {"survey_id": "...", "response_id": "...", "reward_rule": "SURVEY_COMPLETION"}

    Grants a survey reward. The `response_id` is the idempotency key: the same
    survey response can never be rewarded twice. The amount is configured
    centrally (SURVEY_COMPLETION or SURVEY_QUESTION).
    """
    permission_classes = [TokensPermission]

    def post(self, request):
        survey_id = request.data.get("survey_id")
        response_id = request.data.get("response_id")
        reward_rule = request.data.get("reward_rule", "SURVEY_COMPLETION")
        if not response_id or not survey_id:
            return Response(
                {"error": "survey_id and response_id are required", "code": "missing_fields"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = token_service.reward(
                request.user,
                reward_rule,
                reference_key=f"survey:{survey_id}:{response_id}",
                description=f"Survey reward (survey {survey_id})",
                initiated_by="survey",
            )
        except services.TokenError as exc:
            return _error(exc)
        return Response(result, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Purchasing
# ---------------------------------------------------------------------------

class PackageListView(APIView):
    """
    GET /api/tokens/packages/
    Lists active token purchase packages.
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        packages = TokenPackage.objects.filter(is_active=True).order_by("sort_order", "token_amount")
        return Response({"packages": TokenPackageSerializer(packages, many=True).data})


class PurchaseView(APIView):
    """
    POST /api/tokens/purchase/
    Body: {"package_id": "...", "provider": "manual", "payment_reference": "..."}

    Verifies the payment via the payment abstraction, then credits purchased
    tokens. Tokens are NEVER credited because the frontend says payment
    succeeded - the backend verifies the payment first.
    """
    permission_classes = [TokensPermission]

    def post(self, request):
        package_id = request.data.get("package_id")
        payment_reference = request.data.get("payment_reference")
        provider = request.data.get("provider", "manual")
        if not package_id or not payment_reference:
            return Response(
                {"error": "package_id and payment_reference are required", "code": "missing_fields"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from .payments import verify_payment_and_credit
            from .models import TokenPackage

            package = TokenPackage.objects.filter(id=package_id, is_active=True).first()
            if package is None:
                return Response(
                    {"error": "Package not found", "code": "package_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            result = verify_payment_and_credit(
                user=request.user, package=package,
                payment_reference=payment_reference, provider_name=provider,
                currency=package.currency,
            )
        except services.TokenError as exc:
            return _error(exc)
        return Response(result, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------

class RedemptionCreateView(APIView):
    """
    POST /api/tokens/redemptions/
    Body: {"earned_amount": 500, "payout_target": "0712..."}

    Requests redemption of EARNED tokens. The earned tokens are reserved
    (held) until review/approval/complete.
    """
    permission_classes = [TokensPermission]

    def post(self, request):
        earned_amount = request.data.get("earned_amount")
        payout_target = request.data.get("payout_target", "")
        if earned_amount is None:
            return Response(
                {"error": "earned_amount is required", "code": "missing_amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            redemption = token_service.request_redemption(
                request.user, int(earned_amount), payout_target=payout_target
            )
        except services.TokenError as exc:
            return _error(exc)
        return Response(
            RedemptionRequestSerializer(redemption).data, status=status.HTTP_201_CREATED
        )


class RedemptionListView(APIView):
    """
    GET /api/tokens/redemptions/?status=&page=
    Paginated redemption history for the current user.
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        qs = RedemptionRequest.objects.filter(user=request.user)
        s = request.query_params.get("status")
        if s:
            qs = qs.filter(status=s)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            RedemptionRequestSerializer(page if page is not None else qs, many=True).data
        )


class RedemptionStatusView(APIView):
    """
    GET /api/tokens/redemptions/{id}/
    Status of a single redemption request.
    """
    permission_classes = [TokensPermission]

    def get(self, request, pk):
        redemption = RedemptionRequest.objects.filter(user=request.user, pk=pk).first()
        if redemption is None:
            return Response({"error": "Redemption not found", "code": "not_found"},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(RedemptionRequestSerializer(redemption).data)


class RedemptionCancelView(APIView):
    """
    POST /api/tokens/redemptions/{id}/cancel/
    Cancels a PENDING redemption, releasing the held earned tokens.
    """
    permission_classes = [TokensPermission]

    def post(self, request, pk):
        redemption = RedemptionRequest.objects.filter(user=request.user, pk=pk).first()
        if redemption is None:
            return Response({"error": "Redemption not found", "code": "not_found"},
                            status=status.HTTP_404_NOT_FOUND)
        if redemption.status not in ("pending", "approved"):
            return Response(
                {"error": "Only pending or approved redemptions can be cancelled", "code": "invalid_state"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token_service.reject_redemption(redemption, request.user, reason="Cancelled by user")
        return Response({"status": "cancelled", "message": "Redemption cancelled"})


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------

class ReferralCodeView(APIView):
    """
    GET /api/tokens/referral-code/
    Returns the current user's unique referral code (creating it if needed).
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        code = token_service.issue_referral_code(request.user)
        return Response({"referral_code": code.code})


class ReferralView(APIView):
    """
    POST /api/tokens/referrals/
    Body: {"referrer_id": "...", "code": "..."} or {"referred_username"/"referred_email": "..."}

    Registers that a user was referred. Reward only happens once the referred
    user reaches the verified state. Self-referral is blocked.
    """
    permission_classes = [TokensPermission]

    def post(self, request):
        referrer_id = request.data.get("referrer_id") or request.user.pk
        code = request.data.get("code", "")
        referred_email = request.data.get("referred_email")
        referred_username = request.data.get("referred_username")

        from django.contrib.auth import get_user_model
        User = get_user_model()
        referred = None
        if referred_email:
            referred = User.objects.filter(email__iexact=referred_email).first()
        elif referred_username:
            referred = User.objects.filter(username=referred_username).first()
        if referred is None:
            return Response(
                {"error": "Referred user not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        referrer = request.user if str(request.user.pk) == str(referrer_id) else (
            User.objects.filter(pk=referrer_id).first()
        )
        if referrer is None:
            return Response(
                {"error": "Referrer not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            referral = token_service.record_referral(referrer, referred, code=code)
        except services.TokenError as exc:
            return _error(exc)
        return Response({
            "id": str(referral.id),
            "status": referral.status,
            "rewarded": referral.status == "rewarded",
            "referrer_id": str(referral.referrer_id),
            "referred_id": str(referral.referred_id),
        }, status=status.HTTP_201_CREATED)


class ReferralListView(APIView):
    """
    GET /api/tokens/referrals/
    Referrals issued by the current user.
    """
    permission_classes = [TokensPermission]

    def get(self, request):
        qs = Referral.objects.filter(referrer=request.user).select_related("referred")
        data = [
            {
                "id": str(r.id),
                "referred_id": str(r.referred_id),
                "referred_name": r.referred.display_name,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in qs
        ]
        return Response({"referrals": data})


class AdminAdjustmentView(APIView):
    """
    POST /api/tokens/admin/adjust/   (staff only)
    Body: {"user_id": "...", "amount": 50, "stream": "earned|purchased", "reason": "..."}

    Authorized administrators can adjust a user's balance. Always creates an
    auditable ADMIN_ADJUSTMENT transaction, never a silent balance change.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        user_id = request.data.get("user_id")
        amount = request.data.get("amount")
        stream = request.data.get("stream")
        reason = request.data.get("reason", "")

        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not user_id:
            return Response({"error": "user_id is required", "code": "missing_user"},
                            status=status.HTTP_400_BAD_REQUEST)
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response({"error": "User not found", "code": "not_found"},
                            status=status.HTTP_404_NOT_FOUND)
        if amount is None or stream not in ("earned", "purchased"):
            return Response({"error": "amount and stream (earned|purchased) are required", "code": "missing_fields"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            result = token_service.admin_adjust(
                target, int(amount), stream, actor=request.user, reason=reason
            )
        except services.TokenError as exc:
            return _error(exc)
        return Response(result, status=status.HTTP_200_OK)
