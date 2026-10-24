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

    def test_inactive_reward_pays_nothing(self):
        RewardRule.objects.update_or_create(
            key="STORY_SHARE", defaults={"label": "Story", "amount": 10, "is_active": False}
        )
        u = make_user("story@test.com")
        self.assertIsNone(token_service.reward(u, "STORY_SHARE", reference_key="story:1"))
        self.assertEqual(token_service.get_wallet(u).earned_balance, 0)


class ConsumptionOrderingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ConsumptionRule.objects.update_or_create(
            key="GPA_CALCULATION", defaults={"label": "GPA", "amount": 5, "is_active": True}
        )
        RewardRule.objects.update_or_create(
            key="PROFILE_COMPLETION", defaults={"label": "PC", "amount": 50, "is_active": True}
        )

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

    def test_inactive_consumption_is_free(self):
        ConsumptionRule.objects.update_or_create(
            key="MAP_NAVIGATION", defaults={"label": "Map", "amount": 2, "is_active": False}
        )
        u = make_user("free@test.com")
        result = token_service.consume(u, "MAP_NAVIGATION")
        self.assertFalse(result["charged"])
        self.assertEqual(token_service.get_wallet(u).total_balance, 0)

    def test_signup_bonus_once(self):
        RewardRule.objects.update_or_create(
            key="SIGNUP_BONUS", defaults={"label": "Welcome", "amount": 100, "is_active": True}
        )
        u = make_user("new@test.com")
        token_service.grant_signup_bonus(u)
        token_service.grant_signup_bonus(u)
        self.assertEqual(token_service.get_wallet(u).earned_balance, 100)

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
        RewardRule.objects.update_or_create(
            key="PROFILE_COMPLETION", defaults={"label": "PC", "amount": 50, "is_active": True}
        )
        ConsumptionRule.objects.update_or_create(
            key="GPA_CALCULATION", defaults={"label": "GPA", "amount": 5, "is_active": True}
        )
        TokenPackage.objects.create(name="Starter", token_amount=100, price_amount=5000.00, currency="TSH")

    def test_wallet_endpoint(self):
        resp = self.client.get("/api/tokens/wallet/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_balance"], 0)

    def test_consume_endpoint_requires_rule(self):
        resp = self.client.post("/api/tokens/consume/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_consume_endpoint_rejects_server_only_rules(self):
        resp = self.client.post("/api/tokens/consume/", {"rule_key": "MR_CALUU_MESSAGE"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "rule_not_client_chargeable")

    def test_consume_endpoint_blocks_short_balance(self):
        resp = self.client.post("/api/tokens/consume/", {"rule_key": "GPA_CALCULATION"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "insufficient_balance")

    def test_packages_list_returns_active_only(self):
        inactive = TokenPackage.objects.create(
            name="Hidden", token_amount=10, price_amount=100, currency="TSH", is_active=False
        )
        resp = self.client.get("/api/tokens/packages/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("packages", resp.data)
        ids = {str(p["id"]) for p in resp.data["packages"]}
        self.assertNotIn(str(inactive.id), ids)
        self.assertTrue(any(p["name"] == "Starter" for p in resp.data["packages"]))

    def test_purchase_endpoint_is_pending_until_staff_approval(self):
        pkg = TokenPackage.objects.first()
        resp = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "PAY-REF-1", "provider": "manual"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")
        self.assertEqual(token_service.get_wallet(self.user).purchased_balance, 0)
        # Same reference must not create a second request or credit tokens.
        resp2 = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "PAY-REF-1", "provider": "manual"},
            format="json",
        )
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(token_service.get_wallet(self.user).purchased_balance, 0)

        denied = self.client.post(
            f"/api/tokens/admin/purchases/{resp.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        staff = make_user("staff-purchase@test.com")
        staff.is_staff = True
        staff.save()
        self.client.force_authenticate(user=staff)
        approved = self.client.post(
            f"/api/tokens/admin/purchases/{resp.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(token_service.get_wallet(self.user).purchased_balance, 100)
        again = self.client.post(
            f"/api/tokens/admin/purchases/{resp.data['id']}/approve/",
            {},
            format="json",
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(token_service.get_wallet(self.user).purchased_balance, 100)

    def test_admin_purchase_list_puts_pending_first(self):
        pkg = TokenPackage.objects.first()
        denied = self.client.get("/api/tokens/admin/purchases/")
        self.assertEqual(denied.status_code, 403)

        older = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "LIST-OLDER", "claimed_amount": "5000"},
            format="json",
        )
        self.assertEqual(older.status_code, 201)

        staff = make_user("staff-list@test.com")
        staff.is_staff = True
        staff.save()
        self.client.force_authenticate(user=staff)
        approved = self.client.post(f"/api/tokens/admin/purchases/{older.data['id']}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200)

        self.client.force_authenticate(user=self.user)
        pending = self.client.post(
            "/api/tokens/purchase/",
            {"package_id": str(pkg.id), "payment_reference": "LIST-PENDING"},
            format="json",
        )
        self.assertEqual(pending.status_code, 201)

        self.client.force_authenticate(user=staff)
        listed = self.client.get("/api/tokens/admin/purchases/")
        self.assertEqual(listed.status_code, 200)
        statuses = [item["status"] for item in listed.data["results"]]
        self.assertEqual(statuses[0], "pending")
        self.assertIn("approved", statuses)
        row = listed.data["results"][0]
        self.assertEqual(row["user_email"], self.user.email)
        self.assertEqual(row["user_name"], self.user.display_name)
        self.assertEqual(row["package_name"], pkg.name)
        self.assertEqual(int(row["token_amount"]), int(pkg.token_amount))
        self.assertEqual(row["payment_reference"], "LIST-PENDING")
        self.assertIn("price_amount", row)
        self.assertEqual(row["currency"], "TSH")

        only_pending = self.client.get("/api/tokens/admin/purchases/", {"status": "pending"})
        self.assertEqual(only_pending.status_code, 200)
        self.assertEqual([item["status"] for item in only_pending.data["results"]], ["pending"])

    def test_history_and_rewards_endpoints(self):
        token_service.reward(self.user, "PROFILE_COMPLETION", reference_key="h1")
        hist = self.client.get("/api/tokens/history/")
        self.assertEqual(hist.status_code, 200)
        self.assertEqual(hist.data["results"][0]["transaction_type"], "PROFILE_COMPLETION")

        RewardRule.objects.update_or_create(
            key="STORY_SHARE", defaults={"label": "Story Shared", "amount": 10, "is_active": True}
        )
        RewardRule.objects.update_or_create(
            key="OPPORTUNITY_SHARE",
            defaults={"label": "Opportunity Shared", "amount": 25, "is_active": True},
        )
        RewardRule.objects.update_or_create(
            key="ARTICLE_SHARE_REWARD",
            defaults={"label": "Article Share Reward", "amount": 70, "is_active": True},
        )
        RewardRule.objects.update_or_create(
            key="COURSE_CONTRIBUTION",
            defaults={"label": "Course Contribution", "amount": 5, "is_active": True},
        )
        RewardRule.objects.update_or_create(
            key="SIGNUP_BONUS",
            defaults={"label": "New Account Welcome", "amount": 100, "is_active": True},
        )
        rewards = self.client.get("/api/tokens/rewards/")
        self.assertEqual(rewards.status_code, 200)
        keys = [r["key"] for r in rewards.data["rewards"]]
        self.assertEqual(
            keys,
            ["STORY_SHARE", "OPPORTUNITY_SHARE", "ARTICLE_SHARE_REWARD", "COURSE_CONTRIBUTION"],
        )
        self.assertNotIn("SIGNUP_BONUS", keys)
        self.assertTrue(all(r.get("description", "") == "" for r in rewards.data["rewards"]))

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
