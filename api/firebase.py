# api/firebase.py
import firebase_admin
from firebase_admin import credentials
import os
from pathlib import Path

# Get the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Path to Firebase credentials file
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")


def _resolve_credentials_path() -> str | None:
    """Locate a usable Firebase service-account file.

    Precedence:
      1. FIREBASE_CREDENTIALS_PATH from the environment.
      2. firebase-credentials.json (hyphen) in the project root -- the real
         service account.
      3. firebase_credentials.json (underscore) -- kept only as a fallback for
         older checkouts that still have it.

    A placeholder file is worse than no file: it loads without error but every
    issued token then fails verification. So reject anything that still carries
    the "your-firebase-project-id" template value.
    """
    candidates = []
    if FIREBASE_CREDENTIALS_PATH:
        candidates.append(FIREBASE_CREDENTIALS_PATH)
    candidates.append(str(BASE_DIR / "firebase-credentials.json"))
    candidates.append(str(BASE_DIR / "firebase_credentials.json"))

    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                if "your-firebase-project-id" in fh.read():
                    print(f"Ignoring placeholder Firebase credentials at {candidate}")
                    continue
        except OSError:
            continue
        return candidate
    return None


def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    try:
        # Check if Firebase is already initialized
        firebase_admin.get_app()
        return
    except ValueError:
        # Firebase app not initialized, initialize it
        path = _resolve_credentials_path()
        if path:
            try:
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
                print("Firebase Admin SDK initialized successfully")
            except Exception as e:
                print(f"Error initializing Firebase: {e}")
                print("Firebase authentication will not work until credentials are properly configured")
        else:
            print("Warning: no usable Firebase credentials file found")
            print("Firebase authentication will not work until credentials are configured")
            print("Set FIREBASE_CREDENTIALS_PATH, or place firebase-credentials.json in the project root")

# Initialize Firebase when this module is imported
initialize_firebase()
