# api/firebase.py
import firebase_admin
from firebase_admin import credentials
import os
from pathlib import Path

# Get the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Path to Firebase credentials file
FIREBASE_CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH",
    BASE_DIR / "firebase_credentials.json"
)

def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    try:
        # Check if Firebase is already initialized
        firebase_admin.get_app()
    except ValueError:
        # Firebase app not initialized, initialize it
        if os.path.exists(FIREBASE_CREDENTIALS_PATH):
            try:
                cred = credentials.Certificate(str(FIREBASE_CREDENTIALS_PATH))
                firebase_admin.initialize_app(cred)
                print("Firebase Admin SDK initialized successfully")
            except Exception as e:
                print(f"Error initializing Firebase: {e}")
                print("Firebase authentication will not work until credentials are properly configured")
        else:
            print(f"Warning: Firebase credentials file not found at {FIREBASE_CREDENTIALS_PATH}")
            print("Firebase authentication will not work until credentials are configured")
            print("Please set FIREBASE_CREDENTIALS_PATH environment variable or place firebase_credentials.json in the project root")

# Initialize Firebase when this module is imported
initialize_firebase()
