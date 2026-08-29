"""Minimal demo project for altcha-django.

Run:  ALTCHA_DEMO_MODE=local  python example/manage.py runserver
      ALTCHA_DEMO_MODE=sentinel python example/manage.py runserver   # needs Sentinel keys
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "altcha_django",
    "contact",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ]
        },
    }
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

STATIC_URL = "static/"
USE_TZ = True
USE_I18N = True
LANGUAGE_CODE = "en"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- altcha-django ---------------------------------------------------------
_MODE = os.environ.get("ALTCHA_DEMO_MODE", "local")

ALTCHA_COLLECT_STATS = True

# The widget follows Django's active language via its `language` attribute. The
# bundle ships English only; set this True (and add LocaleMiddleware) to also load
# the translations bundle so non-English locales render.
# ALTCHA_WIDGET_I18N = True

if _MODE == "sentinel":
    ALTCHA_VERIFIER = "sentinel"
    # Full challenge URL of your self-hosted Sentinel, API key in the query string:
    #   https://sentinel.example.com/v1/challenge?apiKey=key_...
    ALTCHA_SENTINEL_CHALLENGE_URL = os.environ["ALTCHA_SENTINEL_CHALLENGE_URL"]
    ALTCHA_SENTINEL_API_SECRET = os.environ["ALTCHA_SENTINEL_API_SECRET"]
else:
    ALTCHA_VERIFIER = "local"
    ALTCHA_HMAC_SECRET = os.environ.get("ALTCHA_HMAC_SECRET", "demo-hmac-secret-change-me")
