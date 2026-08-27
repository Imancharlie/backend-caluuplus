from pathlib import Path
from datetime import timedelta
import os
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = config('SECRET_KEY', default='django-insecure-chb@r9zzss$o!gy+_(j6jt)wyxwkuif3ge+e^3$n%+3=ey6bea')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,102.202.74.81,caluu.kodin.co.tz').split(',')

# Firebase initialization
FIREBASE_CREDENTIALS_PATH = os.path.join(BASE_DIR, 'firebase-credentials.json')
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
except ImportError:
    pass

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
    "tokens",
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

# Database - PostgreSQL (fallback to SQLite if not configured)
try:
    db_name = config('DB_NAME', default='caluuplus')
    db_user = config('DB_USER', default='caluuplus_user')
    db_password = config('DB_PASSWORD', default='')
    db_host = config('DB_HOST', default='localhost')
    db_port = config('DB_PORT', default='5432')
    
    # Use PostgreSQL if password is set and PostgreSQL is installed, otherwise fallback to SQLite
    # Temporarily force SQLite until PostgreSQL is installed
    use_postgres = False
    if db_password and db_password != 'your-postgres-password-here':
        try:
            import psycopg2
            # Test connection
            test_conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                connect_timeout=5
            )
            test_conn.close()
            use_postgres = True
        except:
            use_postgres = False
    
    if use_postgres:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": db_name,
                "USER": db_user,
                "PASSWORD": db_password,
                "HOST": db_host,
                "PORT": db_port,
                "OPTIONS": {
                    'connect_timeout': 10,
                }
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
                "OPTIONS": {
                    "timeout": 30,
                    "check_same_thread": False,
                }
            }
        }
except:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "timeout": 30,
                "check_same_thread": False,
            }
        }
    }

# Password validation
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
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = 'api.User'

# API Keys
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')

# Pricing configuration
ANTHROPIC_INPUT_USD_PER_TOKEN = float(config('ANTHROPIC_INPUT_USD_PER_TOKEN', '0.00000025'))
ANTHROPIC_OUTPUT_USD_PER_TOKEN = float(config('ANTHROPIC_OUTPUT_USD_PER_TOKEN', '0.00000125'))
USD_TO_TSH_RATE = float(config('USD_TO_TSH_RATE', '2700'))

# Anthropic API Rate Limiting
ANTHROPIC_MIN_REQUEST_INTERVAL = float(config('ANTHROPIC_MIN_REQUEST_INTERVAL', '3'))

# Chatbot links
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

# CORS settings
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

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
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

# Logging configuration - Production
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
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'api': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'chatbot': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = int(config('EMAIL_PORT', default='587'))
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default='true').lower() == 'true'
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@caluuplus.com')

# Backup Configuration
BACKUP_ROOT = Path(config('BACKUP_ROOT', default=str(BASE_DIR / 'backups_storage')))
BACKUP_NOTIFY_EMAIL = config('BACKUP_NOTIFY_EMAIL', default='')
OPPORTUNITY_REVIEW_NOTIFY_EMAIL = config('OPPORTUNITY_REVIEW_NOTIFY_EMAIL', default='kodinsoftwares@gmail.com')
OPPORTUNITY_ADMIN_REVIEW_URL = config('OPPORTUNITY_ADMIN_REVIEW_URL', default='https://caluu.kodin.co.tz/admin/opportunities')

# Security settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = False  # Set to True if using HTTPS directly
SESSION_COOKIE_SECURE = False  # Set to True if using HTTPS directly
CSRF_COOKIE_SECURE = False  # Set to True if using HTTPS directly
