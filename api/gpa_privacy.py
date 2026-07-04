import base64
import os

from django.conf import settings


def encrypt_gpa_for_user(user, plain_gpa: str):
    """
    Encrypt GPA using a per-user derived key without prompting user.
    The key material combines server secret + user-specific token surface.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = os.urandom(16)
    iv = os.urandom(12)

    # User-specific token surface (rotates on password change)
    user_token = f"{user.id}:{user.password}:{user.email}".encode("utf-8")
    master = settings.SECRET_KEY.encode("utf-8") + b"|" + user_token

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    key = kdf.derive(master)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, str(plain_gpa).encode("utf-8"), None)

    return {
        "gpa_ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "gpa_iv": base64.b64encode(iv).decode("utf-8"),
        "gpa_salt": base64.b64encode(salt).decode("utf-8"),
        "gpa_alg": "AES-GCM-PBKDF2-USERTOKEN-v1",
    }
