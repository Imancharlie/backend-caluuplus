from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from tokens import services as token_service
from tokens.models import (
    ConsumptionRule,
    RedemptionRequest,
    Referral,
    ReferralCode,
    RewardRule,
    TokenEconomyConfig,
    TokenPackage,
    TokenTransaction,
    TokenWallet,
)

User = get_user_model()


def make_user(email="u@test.com"):
    return User.objects.create_user(email=email, username=email, display_name=email.split("@")[0])


class TokenWalletBasicsTest(TestCase):
    def test_wallet_created_and_zero(self):
        u = make_user()
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.total_balance, 0)
        self.assertEqual(wallet.earned_balance, 0)
        self.assertEqual(wallet.purchased_balance, 0)


class RewardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        RewardRule.objects.create(key="PROFILE_COMPLETION", label="PC", amount=50)

    def test_reward_credits_earned(self):
        u = make_user()
        result = token_service.reward(u, "PROFILE_COMPLETION", description="test")
        self.assertEqual(result["earned_balance"], 50)
        self.assertEqual(result["kind"], "earned")
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.earned_balance, 50)
        # Recount ledger
        tx = TokenTransaction.objects.filter(user=u, transaction_type="PROFILE_COMPLETION").first()
        self.assertEqual(int(tx.amount), 50)
        self.assertEqual(tx.kind, "earned")
        # User cached field synced
        u.refresh_from_db()
        self.assertEqual(u.tokens_balance, 50)

    def test_reward_idempotent_by_reference(self):
        u = make_user()
        ref = "unique-ref"
        token_service.reward(u, "PROFILE_COMPLETION", reference_key=ref)
        with self.assertRaises(token_service.DuplicateOperation):
            token_service.reward(u, "PROFILE_COMPLETION", reference_key=ref)
        self.assertEqual(token_service.get_wallet(u).earned_balance, 50)

    def test_reward_inactive_rule_fails(self):
        u = make_user()
        with self.assertRaises(token_service.RuleNotFound):
            token_service.reward(u, "NOT_A_REAL_RULE")


class ConsumptionOrderingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ConsumptionRule.objects.create(key="GPA_CALCULATION", label="GPA", amount=5)
        RewardRule.objects.create(key="PROFILE_COMPLETION", label="PC", amount=50)

    def test_purchased_consumed_first(self):
        u = make_user()
        token_service.purchase(u, amount=500)
        token_service.reward(u, "PROFILE_COMPLETION", amount=200)
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.purchased_balance, 500)
        self.assertEqual(wallet.earned_balance, 200)

        # First consumption draws from purchased.
        token_service.consume(u, "GPA_CALCULATION")
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.purchased_balance, 495)
        self.assertEqual(wallet.earned_balance, 200)

        # Deplete purchased (495 more) then draw from earned.
        for i in range(99):
            token_service.consume(u, "GPA_CALCULATION", reference_key=f"c{i}")
        wallet = token_service.get_wallet(u)
        # 100 consumes total = 500 tokens. Purchased (500) consumed entirely,
        # so earned is untouched.
        self.assertEqual(wallet.purchased_balance, 0)
        self.assertEqual(wallet.earned_balance, 200)

        # One more consume draws from earned.
        token_service.consume(u, "GPA_CALCULATION", reference_key="clast")
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.purchased_balance, 0)
        self.assertEqual(wallet.earned_balance, 195)

    def test_insufficient_balance(self):
        u = make_user()
        with self.assertRaises(token_service.InsufficientBalance):
            token_service.consume(u, "GPA_CALCULATION")

    def test_consume_idempotent(self):
        u = make_user()
        token_service.reward(u, "PROFILE_COMPLETION", amount=50)
        ref = "consume-ref"
        token_service.consume(u, "GPA_CALCULATION", reference_key=ref)
        with self.assertRaises(token_service.DuplicateOperation):
            token_service.consume(u, "GPA_CALCULATION", reference_key=ref)
        self.assertEqual(token_service.get_wallet(u).total_balance, 45)


class PurchaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        TokenPackage.objects.create(name="Starter", token_amount=100, price_amount=5000.00, currency="TSH")

    def test_purchase_credits_purchased(self):
        u = make_user()
        pkg = TokenPackage.objects.first()
        result = token_service.purchase(u, package_id=pkg.id, reference_key=f"purchase:{pkg.id}:pref")
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.purchased_balance, 100)
        self.assertEqual(wallet.earned_balance, 0)
        self.assertEqual(wallet.total_balance, 100)

    def test_purchase_idempotent(self):
        u = make_user()
        pkg = TokenPackage.objects.first()
        ref = f"purchase:{pkg.id}:xyz"
        token_service.purchase(u, package_id=pkg.id, reference_key=ref)
        with self.assertRaises(token_service.DuplicateOperation):
            token_service.purchase(u, package_id=pkg.id, reference_key=ref)
        self.assertEqual(token_service.get_wallet(u).purchased_balance, 100)


class RedemptionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        TokenEconomyConfig.objects.create(
            key="REDEMPTION", value={"enabled": True, "minimum_amount": 50}
        )
        RewardRule.objects.create(key="PROFILE_COMPLETION", label="PC", amount=100)
        TokenPackage.objects.create(name="Starter", token_amount=100, price_amount=5000.00)

    def test_only_earned_can_be_redeemed(self):
        u = make_user()
        token_service.purchase(u, amount=100)  # purchased only
        with self.assertRaises(token_service.InsufficientBalance):
            token_service.request_redemption(u, 50)
        # add earned and redeem from earned
        token_service.reward(u, "PROFILE_COMPLETION", amount=100)
        req = token_service.request_redemption(u, 50)
        self.assertEqual(req.status, "pending")
        self.assertEqual(req.earned_amount, 50)
        # wallet earned is held (deducted as a reservation), not yet finalised
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.earned_balance, 50)
        self.assertEqual(wallet.available_earned, 50)

    def test_redemption_minimum(self):
        u = make_user()
        token_service.reward(u, "PROFILE_COMPLETION", amount=100)
        with self.assertRaises(token_service.TokenError):
            token_service.request_redemption(u, 10)

    def test_redemption_full_flow(self):
        u = make_user()
        token_service.reward(u, "PROFILE_COMPLETION", amount=100)
        req = token_service.request_redemption(u, 50)
        staff = make_user("staff@test.com")
        staff.is_staff = True
        staff.save()

        token_service.approve_redemption(req, staff)
        req.refresh_from_db()
        self.assertEqual(req.status, "approved")

        token_service.complete_redemption(req, staff, payout_ref="PAY-1")
        req.refresh_from_db()
        self.assertEqual(req.status, "completed")
        wallet = token_service.get_wallet(u)
        # 50 held + 50 deducted now
        self.assertEqual(wallet.earned_balance, 50)
        self.assertEqual(wallet.earned_redeemed, 50)

    def test_rejected_releases_tokens(self):
        u = make_user()
        token_service.reward(u, "PROFILE_COMPLETION", amount=100)
        req = token_service.request_redemption(u, 50)
        staff = make_user("staff2@test.com")
        staff.is_staff = True
        staff.save()
        token_service.reject_redemption(req, staff, reason="nope")
        wallet = token_service.get_wallet(u)
        self.assertEqual(wallet.earned_balance, 100)  # released back

    def test_cannot_double_redeem(self):
        u = make_user()
        token_service.reward(u, "PROFILE_COMPLETION", amount=100)
        token_service.request_redemption(u, 50)
        with self.assertRaises(token_service.InsufficientBalance):
            token_service.request_redemption(u, 60)  # only 50 available


class ReferralTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        RewardRule.objects.create(key="REFERRAL_COMPLETED", label="Referral", amount=100)
        TokenEconomyConfig.objects.create(
            key="REFERRAL_REQUIRED_STATE",
            value={"registration": True, "phone_verified": True, "profile_complete": True},
        )

    def test_self_referral_blocked(self):
        u = make_user()
        code = token_service.issue_referral_code(u)
        with self.assertRaises(token_service.TokenError):
            token_service.record_referral(u, u, code=code.code)

    def test_referral_reward_only_after_eligibility(self):
        referrer = make_user("r@test.com")
        referred = make_user("d@test.com")
        referral = token_service.record_referral(referrer, referred, code="x")
        self.assertEqual(referral.status, "pending")  # not eligible yet
        self.assertEqual(token_service.get_wallet(referrer).earned_balance, 0)

        # Become eligible: set phone_verified and a "profile complete" signal.
        referred.phone_verified = True
        referred.bio = "hello"
        referred.save()
        rewarded = token_service.recheck_referral(referral)
        self.assertTrue(rewarded)
        self.assertEqual(token_service.get_wallet(referrer).earned_balance, 100)


class AdminAdjustmentTest(TestCase):
    def test_staff_only_and_auditable(self):
        u = make_user()
        staff = make_user("admin@test.com")
        staff.is_staff = True
        staff.save()
        result = token_service.admin_adjust(u, 50, "earned", actor=staff, reason="bonus")
        self.assertEqual(result["earned_balance"], 50)
        tx = TokenTransaction.objects.filter(user=u, transaction_type="ADMIN_ADJUSTMENT").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.actor, staff)

    def test_non_staff_rejected(self):
        u = make_user()
        normal = make_user("normal@test.com")
        with self.assertRaises(token_service.TokenError):
            token_service.admin_adjust(u, 50, "earned", actor=normal)


class TokenAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("api@test.com")
        self.client.force_authenticate(user=self.user)
        RewardRule.objects.create(key="PROFILE_COMPLETION", label="PC", amount=50)
        ConsumptionRule.objects.create(key="GPA_CALCULATION", label="GPA", amount=5)
        TokenPackage.objects.create(name="Starter", token_amount=100, price_amount=5000.00, currency="TSH")

    def test_wallet_endpoint(self):
        resp = self.client.get("/api/tokens/wallet/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_balance"], 0)

    def test_consume_endpoint_requires_rule(self):
        resp = self.client.post("/api/tokens/consume/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_purchase_endpoint_verifies_payment(self):
        pkg = TokenPackage.objects.first()
        resp = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "PAY-REF-1", "provider": "manual"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["purchased_balance"], 100)
        self.assertEqual(resp.data["kind"], "purchased")
        # Buying the same package with the same payment ref is idempotent -> 409
        resp2 = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "PAY-REF-1", "provider": "manual"},
            format="json",
        )
        self.assertEqual(resp2.status_code, 409)

    def test_history_and_rewards_endpoints(self):
        token_service.reward(self.user, "PROFILE_COMPLETION", reference_key="h1")
        hist = self.client.get("/api/tokens/history/")
        self.assertEqual(hist.status_code, 200)
        self.assertEqual(hist.data["results"][0]["transaction_type"], "PROFILE_COMPLETION")
        rewards = self.client.get("/api/tokens/rewards/")
        self.assertEqual(rewards.status_code, 200)
        rk = {r["key"] for r in rewards.data["rewards"]}
        self.assertIn("PROFILE_COMPLETION", rk)

    def test_redemption_endpoint(self):
        RewardRule.objects.filter(key="PROFILE_COMPLETION").update(amount=500)
        TokenEconomyConfig.objects.create(key="REDEMPTION", value={"enabled": True, "minimum_amount": 50})
        token_service.reward(self.user, "PROFILE_COMPLETION", amount=500)
        resp = self.client.post(
            "/api/tokens/redemptions/", {"earned_amount": 100, "payout_target": "0712"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")

    def test_authentication_required(self):
        anon = APIClient()
        resp = anon.get("/api/tokens/wallet/")
        self.assertEqual(resp.status_code, 401)
