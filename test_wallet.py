"""Test script to reproduce the wallet 500 error."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from tokens.services import get_wallet
from tokens.models import TokenWallet

User = get_user_model()

# Get a test user
user = User.objects.first()
if not user:
    print("No users found in database")
    exit(1)

print(f"Testing with user: {user.email} (id: {user.id})")
print(f"User has tokens_balance field: {hasattr(user, 'tokens_balance')}")
print(f"User tokens_balance value: {getattr(user, 'tokens_balance', 'N/A')}")

# Check if wallet exists
wallet = TokenWallet.objects.filter(user=user).first()
if wallet:
    print(f"Wallet exists: {wallet.id}")
    print(f"Wallet earned_balance: {wallet.earned_balance}")
    print(f"Wallet purchased_balance: {wallet.purchased_balance}")
else:
    print("No wallet found for user")

# Try to get wallet using the service
try:
    wallet = get_wallet(user)
    print(f"get_wallet succeeded: {wallet}")
    print(f"Total balance: {wallet.total_balance}")
except Exception as e:
    print(f"get_wallet failed with error: {e}")
    import traceback
    traceback.print_exc()
