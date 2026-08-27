from django.contrib import admin
from django.utils.html import format_html

from . import services as token_service
from .models import (
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


@admin.register(TokenWallet)
class TokenWalletAdmin(admin.ModelAdmin):
    list_display = ["user", "earned_balance", "purchased_balance", "total", "is_active", "updated_at"]
    search_fields = ["user__email", "user__display_name"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["sync_user_balances"]

    def total(self, obj):
        return obj.total_balance

    def sync_user_balances(self, request, queryset):
        for wallet in queryset:
            wallet.sync_user_cache()
        self.message_user(request, f"{queryset.count()} wallet caches refreshed.")
    sync_user_balances.short_description = "Refresh cached User balances"


@admin.register(TokenTransaction)
class TokenTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "user", "transaction_type", "kind", "amount", "status", "initiated_by", "created_at"
    ]
    list_filter = ["transaction_type", "kind", "status", "initiated_by"]
    search_fields = ["user__email", "user__display_name", "reference_key", "description"]
    readonly_fields = [f.name for f in TokenTransaction._meta.get_fields()]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        # Ledger entries are created by the service, never manually.
        return False

    def has_change_permission(self, request, obj=None):
        # Ledger is immutable/auditable.
        return False


@admin.register(RewardRule)
class RewardRuleAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "amount", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["key", "label"]
    list_editable = ["amount", "is_active"]


@admin.register(ConsumptionRule)
class ConsumptionRuleAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "amount", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["key", "label"]
    list_editable = ["amount", "is_active"]


@admin.register(TokenPackage)
class TokenPackageAdmin(admin.ModelAdmin):
    list_display = ["name", "token_amount", "price_amount", "currency", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    search_fields = ["name"]


@admin.register(TokenEconomyConfig)
class TokenEconomyConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "updated_at"]
    search_fields = ["key"]


@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "code", "created_at"]
    search_fields = ["user__email", "code"]


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ["referrer", "referred", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["referrer__email", "referred__email", "code"]
    actions = ["check_eligibility_now"]

    def check_eligibility_now(self, request, queryset):
        count = 0
        for referral in queryset:
            if referral.status != "rewarded":
                # Use the service so rewards stay auditable.
                if token_service.recheck_referral(referral):
                    count += 1
        self.message_user(request, f"{count} referral(s) became eligible/rewarded.")
    check_eligibility_now.short_description = "Re-check referral eligibility & reward"


@admin.register(RedemptionRequest)
class RedemptionRequestAdmin(admin.ModelAdmin):
    list_display = [
        "user", "earned_amount", "status", "payout_provider", "payout_target",
        "created_at", "updated_at",
    ]
    list_filter = ["status", "payout_provider"]
    search_fields = ["user__email", "user__display_name", "payout_target"]
    actions = ["approve_selected", "reject_selected", "complete_selected"]
    readonly_fields = ["created_at", "updated_at", "hold_transaction", "finalize_transaction"]

    def save_model(self, request, obj, form, change):
        obj.save()

    ##################################################################
    # Admin redemption workflow
    ##################################################################
    def approve_selected(self, request, queryset):
        count = 0
        for r in queryset:
            if r.status in ("pending",):
                token_service.approve_redemption(r, request.user, note="Approved via admin")
                count += 1
        self.message_user(request, f"{count} redemption(s) approved.")
    approve_selected.short_description = "Approve selected redemptions"

    def reject_selected(self, request, queryset):
        count = 0
        for r in queryset:
            if r.status in ("pending", "approved"):
                token_service.reject_redemption(r, request.user, reason="Rejected via admin")
                count += 1
        self.message_user(request, f"{count} redemption(s) rejected and tokens released.")
    reject_selected.short_description = "Reject selected redemptions (release held tokens)"

    def complete_selected(self, request, queryset):
        count = 0
        for r in queryset:
            if r.status in ("approved", "processing"):
                token_service.complete_redemption(r, request.user, payout_ref="admin-manual")
                count += 1
        self.message_user(request, f"{count} redemption(s) completed.")
    complete_selected.short_description = "Mark selected redemptions completed (finalize deduction)"
