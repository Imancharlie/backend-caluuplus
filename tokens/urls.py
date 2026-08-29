from django.urls import path

from . import views

urlpatterns = [
    path("wallet/", views.WalletView.as_view(), name="token-wallet"),
    path("history/", views.WalletHistoryView.as_view(), name="token-history"),
    path("history/<uuid:pk>/", views.TransactionDetailView.as_view(), name="token-transaction-detail"),
    path("rewards/", views.AvailableRewardsView.as_view(), name="token-rewards"),
    path("consume/", views.ConsumeView.as_view(), name="token-consume"),
    path("survey-reward/", views.SurveyRewardView.as_view(), name="token-survey-reward"),
    path("packages/", views.PackageListView.as_view(), name="token-packages"),
    path("purchase/", views.PurchaseView.as_view(), name="token-purchase"),
    path("redemptions/", views.RedemptionCreateView.as_view(), name="token-redemption-create"),
    path("redemptions/<uuid:pk>/", views.RedemptionStatusView.as_view(), name="token-redemption-status"),
    path("redemptions/<uuid:pk>/cancel/", views.RedemptionCancelView.as_view(), name="token-redemption-cancel"),
    path("redemptions/history/", views.RedemptionListView.as_view(), name="token-redemption-history"),
    path("referral-code/", views.ReferralCodeView.as_view(), name="token-referral-code"),
    path("referrals/", views.ReferralView.as_view(), name="token-referral"),
    path("referrals/list/", views.ReferralListView.as_view(), name="token-referral-list"),
    path("admin/adjust/", views.AdminAdjustmentView.as_view(), name="token-admin-adjust"),
    path("admin/rules/", views.AdminRuleListView.as_view(), name="token-admin-rules"),
    path("admin/rules/<uuid:pk>/", views.AdminRuleUpdateView.as_view(), name="token-admin-rule-detail"),
    path("admin/packages/", views.AdminPackageView.as_view(), name="token-admin-packages"),
    path("admin/packages/<uuid:pk>/", views.AdminPackageUpdateView.as_view(), name="token-admin-package-detail"),
    path("admin/redemptions/", views.AdminRedemptionListView.as_view(), name="token-admin-redemptions"),
    path("admin/redemptions/<uuid:pk>/<str:action>/", views.AdminRedemptionReviewView.as_view(), name="token-admin-redemption-review"),
    path("admin/users/", views.AdminUserSearchView.as_view(), name="token-admin-users"),
]
