"""
Payment provider abstraction for Caluu+ token purchases.

The actual payment integration (Flutterwave, Mobile Money, Stripe, etc.) is
isolated here. The token accounting logic in tokens.services NEVER talks to a
payment provider directly - it only recognises an already-verified payment via
its unique reference key.

To add a new provider, subclass PaymentProvider and register it in
PAYMENT_PROVIDERS.
"""

import logging

logger = logging.getLogger(__name__)


class PaymentProvider:
    """Base class for a payment provider."""

    name = "base"

    def create_payment(self, *, user, amount, currency, provider_data):
        """
        Initiate a payment and return a provider-facing payload that the
        frontend can use (checkout URL, payment reference, etc.).
        """
        raise NotImplementedError

    def verify_payment(self, *, payment_reference, expected_amount, expected_currency):
        """
        Verify a payment with the provider.

        Must return a dict with at least:
            {
                "verified": bool,
                "provider_reference": str,
                "amount": <paid amount>,
                "currency": <currency>,
                "metadata": {...},
            }
        """
        raise NotImplementedError


class ManualPaymentProvider(PaymentProvider):
    """
    Placeholder provider for development. It accepts a pre-verified flag or a
    manual confirmation token. NEVER use this as the sole gate in production;
    real verification must come from an actual provider.
    """

    name = "manual"

    def create_payment(self, *, user, amount, currency, provider_data):
        return {
            "provider": self.name,
            "payment_reference": provider_data.get("payment_reference", ""),
            "checkout_needed": False,
        }

    def verify_payment(self, *, payment_reference, expected_amount, expected_currency):
        return {
            "verified": True,
            "provider_reference": payment_reference,
            "amount": int(expected_amount),
            "currency": expected_currency,
            "metadata": {"provider": self.name, "manual": True},
        }


PAYMENT_PROVIDERS = {
    "manual": ManualPaymentProvider,
}


def get_provider(name):
    provider_cls = PAYMENT_PROVIDERS.get(name, ManualPaymentProvider)
    return provider_cls()


def verify_payment_and_credit(*, user, package, payment_reference, provider_name="manual",
                              currency="TSH", actor=None):
    """
    End-to-end flow: verify a payment with the provider, then credit the
    purchased tokens via the token service (guaranteeing the payment is not
    merely trusted from the frontend).

    Returns the purchase result dict.
    """
    from . import services
    from .models import TokenPackage

    provider = get_provider(provider_name)
    verification = provider.verify_payment(
        payment_reference=payment_reference,
        expected_amount=int(package.price_amount),
        expected_currency=currency,
    )
    if not verification or not verification.get("verified"):
        raise services.TokenError(
            "Payment could not be verified", code="payment_not_verified", status_code=400
        )

    reference_key = f"purchase:{package.id}:{payment_reference}"
    return services.purchase(
        user=user,
        package_id=package.id,
        reference_key=reference_key,
        initiated_by="payment",
        actor=actor,
        metadata={"payment_reference": payment_reference, "provider": provider_name},
    )
