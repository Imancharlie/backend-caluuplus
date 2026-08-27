"""
Caluu+ Token Economy.

The token subsystem lives in this app. Feature apps move tokens by importing
the service layer, e.g.:

    from tokens import services as token_service
    token_service.reward(user, "PROFILE_COMPLETION", ...)

NEVER modify wallet balances directly.
"""
