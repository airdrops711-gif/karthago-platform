"""
Django base settings for Karthago Platform.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "apps.core.apps.CoreConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.scraper.apps.ScraperConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # The language of the request (fr / ar) is resolved here, after the
    # session (the language may be stored in it) and before the views.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Tenant resolution: runs after the session and the authentication,
    # because the vendor dashboard needs request.user to find the store.
    "apps.core.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.tenant_context",
                "apps.core.context_processors.language_context",
                "apps.core.context_processors.tunisian_governorates",
                "apps.core.context_processors.cart_item_count",
                "apps.core.context_processors.nav_categories",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRESQL_DATABASE", "dropship_db"),
        "USER": os.getenv("POSTGRESQL_USER", "dropship"),
        "PASSWORD": os.getenv("POSTGRESQL_PASSWORD", "changeme123"),
        "HOST": os.getenv("POSTGRESQL_HOST", "localhost"),
        "PORT": os.getenv("POSTGRESQL_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Bilingual (fr / ar) ----------------------------------------------
# The platform speaks two languages: French (the source language of the
# UI) and Tunisian Arabic. The catalogue files live in ``locale/``.
LANGUAGE_CODE = "fr"

LANGUAGES = [
    ("fr", "Français"),
    ("ar", "العربية"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

# The language chosen by the visitor is kept in a cookie for one year.
LANGUAGE_COOKIE_NAME = "karthago_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

# --- Money and numbers ------------------------------------------------
# The prices are stored in millimes (100.000 DT = 100 dinars 000 millimes),
# so the decimal point is a dot and the thousands are grouped with a comma.
# Django's own ``fr``/``ar`` locale modules would use a comma as the
# decimal separator, so the project ships its own format modules
# (``config/formats/``) which are loaded first.
FORMAT_MODULE_PATH = ["config.formats"]

USE_THOUSAND_SEPARATOR = True
DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3

TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

# The dashboard is staff-only and reuses the Django admin login form.
# Without this, @login_required redirects to /accounts/login/ (404).
LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/dashboard/"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Tunis"

# Meilisearch
MEILISEARCH_HOST = os.getenv("MEILISEARCH_HOST", "http://localhost:7700")
MEILISEARCH_API_KEY = os.getenv("MEILISEARCH_API_KEY", "")

# Tunisian currency
TUNISIAN_CURRENCY = "TND"
TUNISIAN_CURRENCY_DECIMAL_PLACES = 3

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
