# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The Portal's settings. Everything that differs per environment comes from the environment (.env.example)."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
# Where the core's call page is: the test call button and the Call link send a Business's browser there, never to an address taken from a request.
CORE_URL = required("CORE_URL") or "http://localhost:7860"
if not DEBUG and not CORE_URL.startswith(
    "https://"
):  # the ticket travels in this address
    raise ImproperlyConfigured("CORE_URL must be an https address outside a local run")

# Self-hosting's switch, the same one the core reads (voice/modules.py): a local Module, or an http or private address, is accepted only when it is 1. Hosted never sets it.
ALLOW_LOCAL_MODULES = os.environ.get("ALLOW_LOCAL_MODULES", "").strip() == "1"

# The one Account (by email) that may open the totals page. Empty closes the page to everyone.
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "").strip().lower()

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
if not DEBUG:  # a local run's runserver serves static files itself; the image serves the collected ones
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
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
if not DEBUG:
    # Behind the host's proxy, which ends TLS and says so in this header. HSTS is 30 days for now, without subdomains.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 30 * 24 * 3600

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

# Holds the login failure counts; the default 300 entries would let a flood of made-up emails push a real count out.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "OPTIONS": {"MAX_ENTRIES": 100_000},
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = (
    BASE_DIR.parent / "staticfiles"
)  # collectstatic writes here at image build; WhiteNoise serves it
USE_TZ = True  # stored times are UTC
# The clock the Portal shows times on; a name that is not a time zone stops the Portal rather than showing wrong times.
TIME_ZONE = os.environ.get("TIME_ZONE", "").strip() or "UTC"
try:
    ZoneInfo(TIME_ZONE)
except (ZoneInfoNotFoundError, ValueError) as error:
    raise ImproperlyConfigured(
        f"TIME_ZONE {TIME_ZONE!r} is not a time zone name (see .env.example)"
    ) from error
