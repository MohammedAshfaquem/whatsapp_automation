import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
env_file = BASE_DIR / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-key-change-in-production-ac-shop'
)

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')
    if host.strip()
]
# Automatically allow ngrok tunnels for development & Meta WhatsApp webhooks
if DEBUG:
    ALLOWED_HOSTS.extend(['.ngrok-free.app', '.ngrok-free.dev', '.ngrok.io'])

CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.app',
    'https://*.ngrok-free.dev',
    'https://*.ngrok.io',
]
CSRF_TRUSTED_ORIGINS = ([origin.strip() for origin in os.getenv(
    'DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
    + (CSRF_TRUSTED_ORIGINS if DEBUG else []))

if not DEBUG:
    if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure-') or len(set(SECRET_KEY)) < 5:
        raise ImproperlyConfigured('Production requires a strong DJANGO_SECRET_KEY (at least 50 characters).')
    if not os.getenv('DJANGO_ALLOWED_HOSTS') or not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured('Production requires explicit DJANGO_ALLOWED_HOSTS without a wildcard.')

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG and os.getenv('DJANGO_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() in ('true', '1', 'yes')
SECURE_HSTS_PRELOAD = not DEBUG and os.getenv('DJANGO_HSTS_PRELOAD', 'False').lower() in ('true', '1', 'yes')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
# Enable only behind a proxy which strips incoming forwarded headers.
if os.getenv('DJANGO_TRUST_PROXY_HEADERS', 'False').lower() in ('true', '1', 'yes'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'drf_spectacular',
    'corsheaders',

    # Local apps
    'apps.business',
    'apps.services',
    'apps.knowledge_base',
    'apps.chatbot',
    'apps.bookings',
    'apps.whatsapp',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database configuration
# Supports PostgreSQL via DATABASE_URL or defaults to sqlite3 for local development
DATABASE_URL = os.getenv('DATABASE_URL', f"sqlite:///{BASE_DIR / 'db.sqlite3'}")

DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    # Short atomic sections wait for the writer before reading, avoiding upgrade races.
    DATABASES['default'].setdefault('OPTIONS', {}).update(transaction_mode='IMMEDIATE', timeout=20)

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'standard': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# Swagger / OpenAPI Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'AC Service Shop Automation API',
    'DESCRIPTION': 'Interactive API documentation for AC services, simulated AI chat, customer bookings, and WhatsApp integration.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
}

# Business & AC Service settings
DEFAULT_CURRENCY = os.getenv('DEFAULT_CURRENCY', 'INR')

# Gemini AI settings
# Local key edits should take effect even when the IDE/terminal inherited an old key.
# Production keeps deployment environment variables authoritative.
local_gemini_config = dotenv_values(env_file) if DEBUG and env_file.exists() else {}
local_gemini_key = local_gemini_config.get('GEMINI_API_KEY')
GEMINI_API_KEY = local_gemini_key if local_gemini_key is not None else os.getenv('GEMINI_API_KEY', '')
GEMINI_CHAT_MODEL = local_gemini_config.get('GEMINI_CHAT_MODEL') or os.getenv('GEMINI_CHAT_MODEL', 'gemini-flash-latest')
GEMINI_EMBEDDING_MODEL = os.getenv('GEMINI_EMBEDDING_MODEL', 'text-embedding-004')

# Approved template body parameters: booking reference, public status.
WHATSAPP_BOOKING_STATUS_TEMPLATE = os.getenv('WHATSAPP_BOOKING_STATUS_TEMPLATE', '')
WHATSAPP_TEMPLATE_LANGUAGE = os.getenv('WHATSAPP_TEMPLATE_LANGUAGE', 'en')

# ChromaDB settings
CHROMA_PERSIST_DIRECTORY = os.getenv('CHROMA_PERSIST_DIRECTORY', str(BASE_DIR / 'chroma_data'))
CHROMA_COLLECTION_NAME = os.getenv('CHROMA_COLLECTION_NAME', 'ac_shop_knowledge')

# WhatsApp Cloud API settings
WHATSAPP_ENABLED = os.getenv('WHATSAPP_ENABLED', 'False').lower() in ('true', '1', 'yes')
WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
WHATSAPP_PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv('WHATSAPP_BUSINESS_ACCOUNT_ID', '')
WHATSAPP_VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', '')
WHATSAPP_BOOKING_FLOW_ID = os.getenv('WHATSAPP_BOOKING_FLOW_ID', '')
WHATSAPP_TYPING_INDICATOR_ENABLED = os.getenv('WHATSAPP_TYPING_INDICATOR_ENABLED', 'True').lower() in ('true', '1', 'yes')
META_APP_SECRET = os.getenv('META_APP_SECRET', '')
