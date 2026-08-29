"""Settings for the altcha-django test suite."""

from __future__ import annotations

import os

SECRET_KEY = "altcha-django-test-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]
USE_TZ = True
USE_I18N = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "altcha_django",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "default"},
    "shared": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "shared"},
    "dummy": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}
if os.environ.get("ALTCHA_TEST_REDIS_URL"):
    CACHES["redis"] = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["ALTCHA_TEST_REDIS_URL"],
    }

STATIC_URL = "/static/"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("de", "German"), ("fr", "French")]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- altcha-django ------------------------------------------------------------
ALTCHA_HMAC_SECRET = "test-hmac-secret"
# keep proof-of-work trivial so solve_challenge() stays fast in tests:
# counter in [30, 60), cost 50 -> a few ms per solve.
ALTCHA_CHALLENGE = {
    "algorithm": "PBKDF2/SHA-256",
    "cost": 50,
    "max_number": 60,
    "expires_seconds": 600,
}
