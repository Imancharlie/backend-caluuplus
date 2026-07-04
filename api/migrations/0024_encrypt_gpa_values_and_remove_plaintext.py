import base64
import os

from django.conf import settings
from django.db import migrations, models


def _encrypt_legacy_gpa(plain_text: str):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package is required for GPA privacy migration. "
            "Install it, then rerun migrations."
        ) from exc

    salt = os.urandom(16)
    iv = os.urandom(12)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    key = kdf.derive(settings.SECRET_KEY.encode("utf-8"))
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plain_text.encode("utf-8"), None)

    return (
        base64.b64encode(ciphertext).decode("utf-8"),
        base64.b64encode(iv).decode("utf-8"),
        base64.b64encode(salt).decode("utf-8"),
        "AES-GCM-PBKDF2-LEGACY-MIGRATION",
    )


def migrate_plaintext_gpa_to_encrypted(apps, schema_editor):
    GPACalculation = apps.get_model("api", "GPACalculation")
    for row in GPACalculation.objects.all().iterator():
        plain = str(row.gpa)
        cipher, iv, salt, alg = _encrypt_legacy_gpa(plain)
        row.gpa_ciphertext = cipher
        row.gpa_iv = iv
        row.gpa_salt = salt
        row.gpa_alg = alg
        row.save(
            update_fields=["gpa_ciphertext", "gpa_iv", "gpa_salt", "gpa_alg"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0023_backfill_article_category_general"),
    ]

    operations = [
        migrations.AddField(
            model_name="gpacalculation",
            name="gpa_ciphertext",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gpacalculation",
            name="gpa_iv",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="gpacalculation",
            name="gpa_salt",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="gpacalculation",
            name="gpa_alg",
            field=models.CharField(
                default="AES-GCM-PBKDF2",
                max_length=50,
            ),
        ),
        migrations.RunPython(
            migrate_plaintext_gpa_to_encrypted,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="gpacalculation",
            name="gpa",
        ),
        migrations.AlterField(
            model_name="gpacalculation",
            name="gpa_ciphertext",
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name="gpacalculation",
            name="gpa_iv",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="gpacalculation",
            name="gpa_salt",
            field=models.CharField(max_length=128),
        ),
    ]
