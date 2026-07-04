
from pathlib import Path
from datetime import timedelta
import os

# Firebase initialization - optional, only if credentials exist and module is installed
FIREBASE_CREDENTIALS_PATH = os.path.join(Path(__file__).resolve().parent.parent, 'firebase-credentials.json')
FIREBASE_INITIALIZED = False

try:
    import firebase_admin
    from firebase_admin import credentials
    
    if os.path.exists(FIREBASE_CREDENTIALS_PATH):
        try:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            FIREBASE_INITIALIZED = True
        except Exception as e:
            print(f"Warning: Firebase initialization failed: {e}")
            print("Firebase authentication will not be available. Install firebase-admin and provide credentials to enable.")
    else:
        print("Warning: Firebase credentials file not found. Firebase authentication will not be available.")
except ImportError:
    print("Warning: firebase-admin not installed. Firebase authentication will not be available.")
    print("Install with: pip install firebase-admin")
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-chb@r9zzss$o!gy+_(j6jt)wyxwkuif3ge+e^3$n%+3=ey6bea"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",
    "chatbot",
    "data_import",
    "resources_opps",
    "backups",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "academic_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "academic_backend.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 30,  # Increased timeout for database operations
            "check_same_thread": False,  # Allow multiple threads to access database
        }
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Dar_es_Salaam"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (User uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = 'api.User'

# Gemini API Key
# Uses environment variable if set; otherwise falls back to the provided key so you can run without env vars.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "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")

# Pricing configuration 
# Cost per token in USD for Anthropic Claude (Haiku) – adjust as needed
ANTHROPIC_INPUT_USD_PER_TOKEN = float(os.getenv("ANTHROPIC_INPUT_USD_PER_TOKEN", "0.00000025"))
ANTHROPIC_OUTPUT_USD_PER_TOKEN = float(os.getenv("ANTHROPIC_OUTPUT_USD_PER_TOKEN", "0.00000125"))
USD_TO_TSH_RATE = float(os.getenv("USD_TO_TSH_RATE", "2700"))

# Anthropic API Rate Limiting Configuration
# Adjust based on your API tier to prevent rate limit errors while maintaining good UX:
# - Free tier (5 req/min): Use 12 seconds for safety
# - Paid tier (50 req/min): Use 1.2 seconds
# - Development/Testing: Use 2-3 seconds for faster iteration
# Note: Per-user throttling allows multiple users simultaneously
ANTHROPIC_MIN_REQUEST_INTERVAL = float(os.getenv("ANTHROPIC_MIN_REQUEST_INTERVAL", "3"))

# Canonical frontend routes for link tags used by Mr. Caluu
CHATBOT_LINKS = {
    "dashboard": "/dashboard",
    "articles": "/articles",
    "article_detail": "/articles/:id",
    "saved_articles": "/saved-articles",
    "career_guidance": "/career-guidance",
    "chatbot": "/chatbot",
    "gpa_calculator": "/calculator",
    "timetable": "/timetable",
    "workplace": "/workplace",
    "notifications": "/notifications",
    "help_center": "/help-center",
    "settings": "/settings",
    "login": "/login",
    "register": "/register",
    "forgot_password": "/forgot-password",
}

# CORS settings for frontend
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'cache-control',
]
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Allow media files to be accessed from frontend
CORS_URLS_REGEX = r'^/(api|media)/.*$'

# JWT Authentication
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.OptionalJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 12,
}

# JWT Settings
# Extended token lifetimes for better user experience
# Users will stay authenticated for up to 7 days even after closing the tab
SIMPLE_JWT = {
    # Access token valid for 7 days (168 hours)
    # This allows users to stay authenticated even after closing the browser tab
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    
    # Refresh token valid for 14 days (2 weeks)
    # Provides extra buffer for token refresh
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    
    # Rotate refresh tokens on each use for better security
    'ROTATE_REFRESH_TOKENS': True,
    
    # Blacklist old refresh tokens after rotation
    'BLACKLIST_AFTER_ROTATION': True,
    
    # Update last login timestamp
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(days=7),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=14),
}

# Logging configuration - show logs in terminal
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {pathname}:{lineno} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
        'detailed': {
            'format': '[{levelname}] {asctime} [{name}] {pathname}:{lineno}\n{message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',  # Changed to DEBUG to see all logs
    },
    'loggers': {
        'api': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Show all API logs including DEBUG, INFO, WARNING, ERROR
            'propagate': False,
        },
        'chatbot': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',  # Show Django request errors
            'propagate': False,
        },
    },
}

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@caluuplus.com")
BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", BASE_DIR / "backups_storage"))
BACKUP_NOTIFY_EMAIL = os.getenv("BACKUP_NOTIFY_EMAIL", "")
OPPORTUNITY_REVIEW_NOTIFY_EMAIL = os.getenv(
    "OPPORTUNITY_REVIEW_NOTIFY_EMAIL", "kodinsoftwares@gmail.com"
)
OPPORTUNITY_ADMIN_REVIEW_URL = os.getenv(
    "OPPORTUNITY_ADMIN_REVIEW_URL", "https://caluu.kodin.co.tz/admin/opportunities"
)
