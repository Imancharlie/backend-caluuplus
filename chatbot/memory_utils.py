"""
Memory safety filter — prevents sensitive/denylisted information from being
persisted into StudentMemory rows.

This is a single auditable function so the entire sensitive-category policy
lives in one place.
"""

# Categories that must NEVER be auto-stored as StudentMemory
SENSITIVE_CATEGORIES = frozenset([
    'health', 'mental_health', 'medical', 'illness', 'diagnosis', 'medication',
    'family_issue', 'family_struggle', 'relationship', 'dating', 'breakup',
    'financial_hardship', 'money_problem', 'debt', 'poverty',
    'disciplinary', 'suspension', 'expulsion', 'academic_misconduct',
    'trauma', 'abuse', 'self_harm', 'suicide', 'depression', 'anxiety',
    'sexual', 'pregnancy', 'substance', 'drug', 'alcohol',
])

DENYLIST_KEYWORDS = frozenset([
    'sick', 'hospital', 'doctor', 'therapist', 'counselor',
    'depressed', 'anxious', 'suicidal', 'self-harm',
    'parents divorced', 'family problems', 'abusive',
    "can't afford", 'no money', 'financial aid rejected',
    'suspended', 'expelled', 'cheating caught',
    'boyfriend cheated', 'girlfriend left', 'breakup', 'divorce',
    'cancer', 'diabetes', 'medication', 'prescription',
    'evicted', 'homeless', 'starving',
])


def is_sensitive_value(value: str) -> bool:
    """Check if a memory value contains any denylisted keyword."""
    if not value:
        return False
    value_lower = value.lower()
    return any(kw in value_lower for kw in DENYLIST_KEYWORDS)


def is_sensitive_key(key: str) -> bool:
    """Check if a memory key is in the sensitive category list."""
    if not key:
        return False
    key_lower = key.lower().strip()
    return key_lower in SENSITIVE_CATEGORIES


def should_store_memory(key: str, value: str) -> bool:
    """Determine whether a memory candidate should be persisted.

    Returns False if the key is a sensitive category or the value contains
    any denylisted keyword. This is the single auditable gate for what gets
    written to StudentMemory.
    """
    if is_sensitive_key(key):
        return False
    if is_sensitive_value(value):
        return False
    return True
