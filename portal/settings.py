# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The Portal's settings. Everything that differs per environment comes from the environment (.env.example)."""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent

# Fail closed: the Portal says where it runs, and DEBUG (which switches off every required value below) is allowed only locally.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "")
if ENVIRONMENT not in ("local", "production"):
    raise ImproperlyConfigured(
        "ENVIRONMENT must be local or production (see .env.example)"
    )
DEBUG = os.environ.get("DEBUG") == "1"
if DEBUG and ENVIRONMENT != "local":
    raise ImproperlyConfigured(
        "DEBUG is on outside a local run: it switches off every check in this file"
    )


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value and not DEBUG:
        raise ImproperlyConfigured(f"{name} is not set (see .env.example)")
    return value


SECRET_KEY = required("DJANGO_SECRET_KEY") or "local-only-not-secret"
ALLOWED_HOSTS = (
    ["*"] if DEBUG else [h.strip() for h in required("ALLOWED_HOSTS").split(",")]
)
# The address invite links point at; never taken from a request's Host header.
PORTAL_URL = required("PORTAL_URL") or "http://localhost:8000"
# The shared secret the core sends to fetch a Business's settings. Empty (only possible on a local run) refuses every request.
CORE_SECRET = required("CORE_SECRET")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "portal.accounts",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "portal.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]

# An empty DATABASE_URL leaves the dummy backend in place, so any query fails with a clear message.
DATABASES = {
    "default": dj_database_url.parse(os.environ["DATABASE_URL"])
    if os.environ.get("DATABASE_URL")
    else {}
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.Account"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
PASSWORD_RESET_TIMEOUT = (
    7 * 24 * 3600
)  # an invite link lives a week; a reset link works the same way

SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG

if os.environ.get("EMAIL_HOST"):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": os.environ["EMAIL_HOST"],
                "port": int(os.environ.get("EMAIL_PORT", "587")),
                "username": os.environ.get("EMAIL_HOST_USER", ""),
                "password": os.environ.get("EMAIL_HOST_PASSWORD", ""),
                "use_tls": True,
            },
        }
    }
    DEFAULT_FROM_EMAIL = required("EMAIL_FROM")
elif DEBUG:
    # Invite and reset links are credentials: they print to the console on a local run only.
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
else:
    raise ImproperlyConfigured("EMAIL_HOST is not set (see .env.example)")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
USE_TZ = True
TIME_ZONE = "UTC"
