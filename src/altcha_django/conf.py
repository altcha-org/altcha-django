"""Typed access to ``ALTCHA_*`` settings with defaults, caching and deprecations.

Usage::

    from altcha_django.conf import conf
    conf.HMAC_SECRET          # -> settings.ALTCHA_HMAC_SECRET or the default
    conf.CHALLENGE["cost"]    # nested dicts are merged over the defaults

The accessor caches resolved values and transparently clears itself when
``@override_settings`` (or any ``setting_changed`` signal) fires, so tests do not
need to poke at internals.
"""

from __future__ import annotations

import copy
from typing import Any

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

PREFIX = "ALTCHA_"

#: name -> default value. The public setting name is ``ALTCHA_<NAME>``.
DEFAULTS: dict[str, Any] = {
    # --- verifier selection -------------------------------------------------
    "VERIFIER": "local",
    "VERIFIER_OPTIONS": {},
    # --- local proof-of-work ---------------------------------------------
    "HMAC_SECRET": None,
    "HMAC_ALGORITHM": "SHA-256",
    "CHALLENGE": {
        "algorithm": "PBKDF2/SHA-256",
        "cost": 5000,
        "key_prefix": "00",  # probabilistic difficulty (hex prefix); longer = harder
        "max_number": None,  # set an int -> deterministic mode (counter upper bound)
        "expires_seconds": 600,
        "key_length": 32,
        "memory_cost": None,  # KiB, Argon2id / scrypt only
        "parallelism": None,
    },
    "CHALLENGE_HMAC_KEY_SECRET": None,
    "CHALLENGE_BIND_SESSION": False,
    "CHALLENGE_ENDPOINT_ENABLED": True,
    "CHALLENGE_ENDPOINT_RATELIMIT": None,
    # IPs/CIDRs of proxies allowed to set X-Forwarded-For. Empty (the default)
    # means the header is ignored entirely and REMOTE_ADDR is used.
    "TRUSTED_PROXIES": [],
    "WIDGET_CHALLENGE_MODE": "auto",
    # --- replay protection ---------------------------------------------
    "CACHE_ALIAS": "default",
    "REPLAY_PROTECTION": True,
    "REPLAY_KEY_PREFIX": "altcha:replay:",
    "REPLAY_FALLBACK_TTL": 3600,
    "REPLAY_CLOCK_SKEW": 30,
    # --- test / dev ----------------------------------------------------
    "TEST_MODE": False,
    # --- widget ------------------------------------------------------------
    "WIDGET_JS_SOURCE": "vendored",  # vendored | cdn | custom
    "WIDGET_JS_URL": None,
    "WIDGET_JS_CDN": "https://cdn.jsdelivr.net/npm/altcha@3/dist/main/altcha.min.js",
    "WIDGET_I18N": False,
    "WIDGET_I18N_JS_URL": None,
    "WIDGET_I18N_JS_CDN": "https://cdn.jsdelivr.net/npm/altcha@3/dist/i18n/all.js",
    "WIDGET_DEFAULTS": {"type": "checkbox", "display": "standard"},
    "WIDGET_CONFIGURATION": {},
    # --- stats -------------------------------------------------------------
    "COLLECT_STATS": False,
    # --- Sentinel (self-hosted) ----------------------------------------
    # The full challenge URL of your Sentinel instance, API key already in the
    # query string, e.g. "https://sentinel.example.com/v1/challenge?apiKey=key_..."
    "SENTINEL_CHALLENGE_URL": None,
    # The API key's secret, used to verify the signed payload locally.
    "SENTINEL_API_SECRET": None,
    # Optional: override the /v1/verify/signature URL (else derived from the
    # challenge URL). Only used when SENTINEL_MODE == "remote".
    "SENTINEL_VERIFY_URL": None,
    "SENTINEL_MODE": "local",  # local | remote
    "SENTINEL_MIN_SCORE": None,
    "SENTINEL_REJECT_CLASSIFICATIONS": ["BAD"],
    "SENTINEL_VERIFY_FIELDS": True,
    "SENTINEL_SPAMFILTER": False,
    "SENTINEL_PROXY_CHALLENGE": False,
    "SENTINEL_TIMEOUT": 10.0,
    "SENTINEL_RETRIES": 1,
    "SENTINEL_HTTP_POST": None,
    "SENTINEL_HTTP_GET": None,
}

#: dicts here are deep-merged over their default rather than replaced wholesale.
_MERGE_DICTS = frozenset({"CHALLENGE", "WIDGET_DEFAULTS"})

#: old setting name -> (new name, note). Values are still honoured; ``checks.W010``
#: nudges users to migrate.
DEPRECATED: dict[str, tuple[str, str]] = {
    "HMAC_KEY": ("HMAC_SECRET", "ALTCHA_HMAC_KEY is deprecated; use ALTCHA_HMAC_SECRET."),
    "JS_URL": ("WIDGET_JS_URL", "ALTCHA_JS_URL is deprecated; use ALTCHA_WIDGET_JS_URL."),
    "JS_TRANSLATIONS_URL": (
        "WIDGET_I18N_JS_URL",
        "ALTCHA_JS_TRANSLATIONS_URL is deprecated; use ALTCHA_WIDGET_I18N_JS_URL.",
    ),
    "INCLUDE_TRANSLATIONS": (
        "WIDGET_I18N",
        "ALTCHA_INCLUDE_TRANSLATIONS is deprecated; use ALTCHA_WIDGET_I18N.",
    ),
}


class AppSettings:
    """Lazy, cached accessor for ``ALTCHA_*`` settings."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    # -- internal --------------------------------------------------------
    def _raw(self, name: str) -> Any:
        return getattr(settings, PREFIX + name, _UNSET)

    def _resolve(self, name: str) -> Any:
        if name not in DEFAULTS:
            raise AttributeError(f"Unknown ALTCHA setting {name!r}")

        default = DEFAULTS[name]
        value = self._raw(name)

        # deprecated-name fallback (also triggers when the new name is explicitly None)
        if value is _UNSET or value is None:
            for old, (new, _note) in DEPRECATED.items():
                if new == name and self._raw(old) not in (_UNSET, None):
                    value = self._raw(old)
                    break

        # legacy ALTCHA_VERIFICATION_ENABLED = False  ->  null verifier
        if name == "VERIFIER" and value is _UNSET:
            if getattr(settings, PREFIX + "VERIFICATION_ENABLED", True) is False:
                return "null"

        # legacy ALTCHA_CHALLENGE_EXPIRE (milliseconds)
        if name == "CHALLENGE":
            merged = _deep_merge(copy.deepcopy(default), value if value is not _UNSET else {})
            legacy_ms = getattr(settings, PREFIX + "CHALLENGE_EXPIRE", None)
            if legacy_ms is not None and (
                value is _UNSET or "expires_seconds" not in (value or {})
            ):
                merged["expires_seconds"] = int(legacy_ms) // 1000
            return merged

        # legacy ALTCHA_JS_URL implies a custom source
        if name == "WIDGET_JS_SOURCE" and value is _UNSET:
            if getattr(settings, PREFIX + "JS_URL", None) is not None:
                return "custom"

        if value is _UNSET:
            return copy.deepcopy(default) if isinstance(default, (dict, list)) else default

        if name in _MERGE_DICTS and isinstance(value, dict):
            return _deep_merge(copy.deepcopy(default), value)

        return value

    # -- public -----------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cache:
            self._cache[name] = self._resolve(name)
        return self._cache[name]

    def clear_cache(self) -> None:
        self._cache.clear()

    # -- derived helpers ------------------------------------------------
    def deprecated_in_use(self) -> list[str]:
        """Return the notes for every deprecated setting currently defined."""
        notes = []
        for old, (_new, note) in DEPRECATED.items():
            if self._raw(old) is not _UNSET:
                notes.append(note)
        if getattr(settings, PREFIX + "CHALLENGE_EXPIRE", None) is not None:
            notes.append(
                "ALTCHA_CHALLENGE_EXPIRE is deprecated; use "
                "ALTCHA_CHALLENGE['expires_seconds'] (seconds, not milliseconds)."
            )
        if hasattr(settings, PREFIX + "VERIFICATION_ENABLED"):
            notes.append("ALTCHA_VERIFICATION_ENABLED is deprecated; set ALTCHA_VERIFIER='null'.")
        return notes


class _Unset:
    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<unset>"

    def __bool__(self) -> bool:
        return False


_UNSET = _Unset()


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


conf = AppSettings()


@receiver(setting_changed)
def _reset_on_change(*, setting: str, **_kwargs: object) -> None:
    if setting.startswith(PREFIX) or setting in {"CACHES", "STATIC_URL", "LANGUAGES"}:
        conf.clear_cache()
