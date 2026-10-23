"""Django settings for the Boredom game server.

Configuration comes from environment variables (see ../.env.example):
DJANGO_DEBUG, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, DATABASE_URL,
ADMIN_URL_PREFIX, TIME_ZONE, CSRF_TRUSTED_ORIGINS.
"""

import os
from pathlib import Path

import dj_database_url
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

from games.constants import PASSWORD_MIN_LENGTH

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable ("1", "true", "yes", "on" are true)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable into a list of non-empty items."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = _env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")
    SECRET_KEY = "django-insecure-dev-only-key-not-for-production"

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
# Origins allowed to POST with cookies (the admin and the React admin dashboard), e.g.
# https://api.example.com. In development the Vite dev server (:5173) proxies to Django.
CSRF_TRUSTED_ORIGINS = _env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else ""
)

# The admin dashboard lives at /<ADMIN_URL_PREFIX>. Pick something unguessable in production.
ADMIN_URL_PREFIX = os.environ.get("ADMIN_URL_PREFIX", "manage/").strip("/") + "/"

# Account requests carry their token in the Authorization header (part of default_headers).
CORS_ALLOW_HEADERS = default_headers


# Application definition

INSTALLED_APPS = [
    "daphne",
    "analytics.admin_apps.BoredomAdminConfig",  # django.contrib.admin with the dashboard site
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "channels",
    "accounts",
    "analytics",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise (production static files) is inserted here when DEBUG is off.
    "analytics.middleware.AdminNoIndexMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Rooms live in this process's memory, so the server must run as ONE process.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


# Database: accounts only (rooms and games stay in memory). DATABASE_URL selects it
# (Postgres in production, with persistent health-checked connections); without it,
# local development uses SQLite.

_USE_DATABASE_URL = bool(os.environ.get("DATABASE_URL"))
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600 if _USE_DATABASE_URL else 0,
        conn_health_checks=_USE_DATABASE_URL,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")  # for display; times are stored in UTC
USE_I18N = True
USE_TZ = True


# Static files (only the admin has any). WhiteNoise serves them; run collectstatic on deploy.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

if not DEBUG:  # with DEBUG on, runserver serves static files itself
    MIDDLEWARE.insert(2, "whitenoise.middleware.WhiteNoiseMiddleware")

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


# Security (admin cookies). Production runs behind an HTTPS proxy that sets X-Forwarded-Proto.

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "rooms": {"handlers": ["console"], "level": "INFO"},
        "games": {"handlers": ["console"], "level": "INFO"},
        "accounts": {"handlers": ["console"], "level": "INFO"},
        "analytics": {"handlers": ["console"], "level": "INFO"},
    },
}
