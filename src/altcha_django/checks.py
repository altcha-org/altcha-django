"""``django.core.checks`` for common misconfiguration."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from django.core.cache import caches
from django.core.checks import CheckMessage, Error, Info, Tags, Warning, register

from .challenge import ChallengeConfig
from .conf import conf
from .exceptions import AltchaConfigurationError

_TAG = "altcha"

#: ChallengeConfig field -> check id. Fields not listed report as ``altcha.E013``.
_CHALLENGE_CHECK_IDS = {"algorithm": "altcha.E009", "key_prefix": "altcha.E010"}

#: Below this, deterministic mode bounds the client's work at a trivial number of
#: KDF evaluations.
_MIN_RECOMMENDED_MAX_NUMBER = 1000

#: Oldest ``altcha`` release that returns a result (instead of raising) for malformed
#: solutions and server-signature payloads. Keep in sync with pyproject.toml.
_MIN_ALTCHA_VERSION = (2, 3, 0)
_ALTCHA_INSTALL_HINT = f"pip install 'altcha>={'.'.join(map(str, _MIN_ALTCHA_VERSION))}'"


def _altcha_version() -> tuple[int, ...] | None:
    try:
        raw = metadata.version("altcha")
    except metadata.PackageNotFoundError:  # pragma: no cover - always installed in tests
        return None
    parts: list[int] = []
    for chunk in raw.split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _check_replay_cache(cache_backend: object) -> list[CheckMessage]:
    """Backends that cannot hold single-use claims reliably across requests."""
    from django.core.cache.backends.dummy import DummyCache
    from django.core.cache.backends.filebased import FileBasedCache
    from django.core.cache.backends.locmem import LocMemCache

    if isinstance(cache_backend, DummyCache):
        return [
            Error(
                "Replay protection is enabled but ALTCHA_CACHE_ALIAS uses DummyCache, "
                "which stores nothing: every solved payload can be reused.",
                id="altcha.E014",
                hint="Point ALTCHA_CACHE_ALIAS at a real shared cache, or set "
                "ALTCHA_REPLAY_PROTECTION = False to accept reuse explicitly.",
            )
        ]
    if isinstance(cache_backend, LocMemCache):
        return [
            Warning(
                "Replay protection uses LocMemCache, which is per-process.",
                id="altcha.W001",
                hint="Use a shared cache (Redis/Memcached/DB) for multi-worker deployments.",
            )
        ]
    if isinstance(cache_backend, FileBasedCache):
        return [
            Warning(
                "Replay protection uses FileBasedCache, whose add() is check-then-set: "
                "concurrent submissions of one payload can both be accepted.",
                id="altcha.W017",
                hint="Use Redis, Memcached or the database cache for ALTCHA_CACHE_ALIAS.",
            )
        ]
    return []


def _verifier_class() -> type | None:
    from .verifiers import _load_class

    try:
        return _load_class(conf.VERIFIER)
    except Exception:
        return None


def _is_local(cls: type | None) -> bool:
    from .verifiers import LocalVerifier, NullVerifier

    return cls is not None and issubclass(cls, (LocalVerifier, NullVerifier))


def _is_sentinel(cls: type | None) -> bool:
    from .verifiers import SentinelVerifier

    return cls is not None and issubclass(cls, SentinelVerifier)


def _is_local_pow(cls: type | None) -> bool:
    """Only the real proof-of-work backend — unlike :func:`_is_local`, not the null one."""
    from .verifiers import LocalVerifier

    return cls is not None and issubclass(cls, LocalVerifier)


def _check_challenge_config() -> list[CheckMessage]:
    """Run :meth:`ChallengeConfig.problems` so ``manage.py check`` reports what
    issuing a challenge would raise."""
    try:
        cfg = ChallengeConfig.from_settings()
    except AltchaConfigurationError as exc:
        return [Error(str(exc), id="altcha.E013")]
    return [
        Error(message, id=_CHALLENGE_CHECK_IDS.get(field, "altcha.E013"))
        for field, message in cfg.problems()
    ]


def _check_session_binding(cls: type | None) -> list[CheckMessage]:
    """``ALTCHA_CHALLENGE_BIND_SESSION`` only works via the challenge endpoint.

    Binding is recorded when :class:`~altcha_django.views.ChallengeView` hands out a
    challenge, so a challenge minted inline (or by a backend that does not implement
    binding) can never be redeemed — every verification would fail. These checks turn
    that silent, total failure into a startup error.
    """
    from django.conf import settings

    if not conf.CHALLENGE_BIND_SESSION:
        return []

    errors: list[CheckMessage] = []

    has_app = "django.contrib.sessions" in settings.INSTALLED_APPS
    has_middleware = any("SessionMiddleware" in mw for mw in settings.MIDDLEWARE)
    if not (has_app and has_middleware):
        errors.append(
            Error(
                "ALTCHA_CHALLENGE_BIND_SESSION is on but Django sessions are not configured.",
                id="altcha.E011",
                hint="Add 'django.contrib.sessions' to INSTALLED_APPS and "
                "'django.contrib.sessions.middleware.SessionMiddleware' to MIDDLEWARE.",
            )
        )

    if cls is None:
        return errors  # unresolvable verifier — E002 already covers it
    if not _is_local_pow(cls):
        errors.append(
            Warning(
                "ALTCHA_CHALLENGE_BIND_SESSION has no effect with this verifier; "
                "session binding is implemented by the local proof-of-work backend.",
                id="altcha.W013",
            )
        )
        return errors

    if not conf.REPLAY_PROTECTION:
        errors.append(
            Warning(
                "ALTCHA_CHALLENGE_BIND_SESSION is on but replay protection is off; session "
                "binding alone does not stop a solved challenge from being reused.",
                id="altcha.W018",
                hint="Removing the token from the session is not atomic, and with "
                "signed-cookie sessions a client can resend its earlier cookie. Keep "
                "ALTCHA_REPLAY_PROTECTION = True.",
            )
        )

    mode = conf.WIDGET_CHALLENGE_MODE
    if mode == "inline":
        errors.append(
            Error(
                "ALTCHA_CHALLENGE_BIND_SESSION is on but ALTCHA_WIDGET_CHALLENGE_MODE="
                "'inline'; inline challenges are never bound to a session, so every "
                "verification would fail.",
                id="altcha.E006",
                hint="Use ALTCHA_WIDGET_CHALLENGE_MODE='endpoint' (or 'auto' with the "
                "URLs wired), or turn off ALTCHA_CHALLENGE_BIND_SESSION.",
            )
        )
    else:
        from django.urls import NoReverseMatch, reverse

        try:
            reverse("altcha_django:challenge")
        except NoReverseMatch:
            errors.append(
                Error(
                    "ALTCHA_CHALLENGE_BIND_SESSION is on but the challenge endpoint is not "
                    "wired, so the widget mints challenges inline and no challenge can be "
                    "redeemed.",
                    id="altcha.E006",
                    hint="Add path('altcha/', include('altcha_django.urls')) to your "
                    "URLconf, or turn off ALTCHA_CHALLENGE_BIND_SESSION.",
                )
            )

    return errors


def _check_widget_defaults() -> list[CheckMessage]:
    """``ALTCHA_WIDGET_DEFAULTS`` holds element *attributes*, nothing else.

    The v3 custom element observes a fixed, small attribute set; anything else put
    here is rendered onto the tag and silently ignored by the browser. Options like
    ``hideLogo`` or ``minDuration`` belong in ``ALTCHA_WIDGET_CONFIGURATION``, which
    is serialised into the ``configuration`` JSON attribute the widget does read.
    """
    from .widgets import ELEMENT_ATTRS, WIDGET_MANAGED_ATTRS

    unknown = sorted(set(conf.WIDGET_DEFAULTS) - set(ELEMENT_ATTRS))
    if not unknown:
        return []

    managed = [key for key in unknown if key in WIDGET_MANAGED_ATTRS]
    hint = (
        f"Valid keys: {', '.join(sorted(ELEMENT_ATTRS))}. Everything else the widget "
        "understands (hideLogo, hideFooter, minDuration, debug, ...) goes in "
        "ALTCHA_WIDGET_CONFIGURATION."
    )
    if managed:
        hint += (
            f" {', '.join(managed)} is set by altcha-django itself — use the field's "
            "own arguments (challenge=, challenge_url=, configuration=) instead."
        )
    return [
        Warning(
            "ALTCHA_WIDGET_DEFAULTS contains keys that are not <altcha-widget> "
            f"attributes and will be ignored by the browser: {', '.join(unknown)}.",
            id="altcha.W014",
            hint=hint,
        )
    ]


def _check_trusted_proxies() -> list[CheckMessage]:
    """Every ``ALTCHA_TRUSTED_PROXIES`` entry must parse as an IP or CIDR network.

    An unparseable entry never matches, so the proxy it was meant to describe stays
    untrusted and ``X-Forwarded-For`` is quietly ignored for it — the setting looks
    applied but is not.
    """
    import ipaddress

    values = conf.TRUSTED_PROXIES
    if isinstance(values, (str, bytes)):
        return [
            Error(
                "ALTCHA_TRUSTED_PROXIES must be a list of IPs/CIDRs, not a string.",
                id="altcha.E012",
                hint='Use ["10.0.0.0/8"], not "10.0.0.0/8".',
            )
        ]

    bad = []
    for value in values:
        try:
            ipaddress.ip_network(str(value), strict=False)
        except ValueError:
            bad.append(str(value))
    if bad:
        return [
            Error(
                f"ALTCHA_TRUSTED_PROXIES contains entries that are not valid IP addresses "
                f"or CIDR networks: {', '.join(bad)}.",
                id="altcha.E012",
                hint="They would never match, leaving X-Forwarded-For untrusted for "
                "those proxies. Example: ['10.0.0.0/8', '192.168.1.5', '2001:db8::/32'].",
            )
        ]
    return []


@register(_TAG)
def check_config(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    version = _altcha_version()
    if version is None:
        errors.append(
            Error(
                "The 'altcha' package is not installed.",
                id="altcha.E001",
                hint=_ALTCHA_INSTALL_HINT,
            )
        )
    elif version < _MIN_ALTCHA_VERSION:
        errors.append(
            Error(
                f"altcha {'.'.join(map(str, version))} is too old; older releases raise "
                "on malformed payloads instead of rejecting them.",
                id="altcha.E001",
                hint=_ALTCHA_INSTALL_HINT,
            )
        )

    cls = _verifier_class()
    if cls is None:
        errors.append(
            Error(
                f"ALTCHA_VERIFIER={conf.VERIFIER!r} could not be resolved.",
                id="altcha.E002",
                hint="Use 'local', 'sentinel', 'null', or a dotted path to a BaseVerifier.",
            )
        )

    if _is_local(cls) and not conf.TEST_MODE and not conf.HMAC_SECRET:
        from .verifiers import NullVerifier

        if not (cls and issubclass(cls, NullVerifier)):
            errors.append(
                Error(
                    "Local ALTCHA verification requires a signing secret.",
                    id="altcha.E003",
                    hint="Set ALTCHA_HMAC_SECRET to a long random string.",
                )
            )

    if _is_sentinel(cls):
        challenge_url = conf.SENTINEL_CHALLENGE_URL
        if not challenge_url:
            errors.append(
                Error(
                    "Sentinel requires the full challenge URL of your instance.",
                    id="altcha.E005",
                    hint="Set ALTCHA_SENTINEL_CHALLENGE_URL "
                    "(e.g. 'https://sentinel.example.com/v1/challenge?apiKey=key_...').",
                )
            )
        elif not str(challenge_url).lower().startswith(("http://", "https://")):
            errors.append(
                Error(
                    f"ALTCHA_SENTINEL_CHALLENGE_URL={challenge_url!r} is not an absolute URL.",
                    id="altcha.E005",
                )
            )
        if conf.SENTINEL_MODE == "local" and not conf.SENTINEL_API_SECRET:
            errors.append(
                Error(
                    "Local Sentinel signature verification requires the API key secret.",
                    id="altcha.E004",
                    hint="Set ALTCHA_SENTINEL_API_SECRET, or use ALTCHA_SENTINEL_MODE='remote'.",
                )
            )

    try:
        cache_backend = caches[conf.CACHE_ALIAS]
    except Exception:
        cache_backend = None
        errors.append(
            Error(
                f"ALTCHA_CACHE_ALIAS={conf.CACHE_ALIAS!r} is not in settings.CACHES.",
                id="altcha.E007",
            )
        )

    if conf.WIDGET_JS_SOURCE == "custom" and not conf.WIDGET_JS_URL:
        errors.append(
            Error(
                "ALTCHA_WIDGET_JS_SOURCE='custom' but ALTCHA_WIDGET_JS_URL is not set.",
                id="altcha.E008",
            )
        )

    errors.extend(_check_challenge_config())

    # --- warnings ---------------------------------------------------
    if conf.REPLAY_PROTECTION and cache_backend is not None:
        errors.extend(_check_replay_cache(cache_backend))
    if not conf.REPLAY_PROTECTION:
        errors.append(
            Warning(
                "ALTCHA replay protection is disabled; solved challenges can be reused.",
                id="altcha.W003",
            )
        )

    # A non-dict ALTCHA_CHALLENGE is reported by altcha.E013.
    challenge = conf.CHALLENGE if isinstance(conf.CHALLENGE, dict) else {}
    if str(challenge.get("algorithm", "")).upper() == "ARGON2ID":
        try:
            import argon2  # noqa: F401
        except ImportError:
            errors.append(
                Warning(
                    "Challenge algorithm is ARGON2ID but argon2-cffi is not installed.",
                    id="altcha.W005",
                    hint="pip install 'altcha-django[argon2]'",
                )
            )
    # Non-integer values are reported by altcha.E013; only compare real integers here.
    cost = challenge.get("cost", 0)
    if isinstance(cost, int) and cost and not 1000 <= cost <= 500_000:
        errors.append(
            Warning(
                f"Challenge cost {cost} is outside the recommended 1000-500000 range.",
                id="altcha.W006",
            )
        )
    expires = challenge.get("expires_seconds", 0)
    if isinstance(expires, int) and expires and not 60 <= expires <= 3600:
        errors.append(
            Warning(
                f"Challenge expiry {expires}s is unusual (recommended 60-3600).", id="altcha.W007"
            )
        )
    max_number = challenge.get("max_number")
    if isinstance(max_number, int) and 0 < max_number < _MIN_RECOMMENDED_MAX_NUMBER:
        errors.append(
            Warning(
                f"Challenge max_number {max_number} bounds each solve at {max_number} KDF "
                f"evaluations (recommended >= {_MIN_RECOMMENDED_MAX_NUMBER}).",
                id="altcha.W016",
                hint="The secret counter lies in [max_number // 2, max_number); with a "
                "small bound the client finds it almost immediately.",
            )
        )

    if conf.WIDGET_JS_SOURCE == "vendored":
        from django.contrib.staticfiles.finders import find

        try:
            found = find("altcha_django/altcha.min.js")
        except Exception:
            found = None
        if not found:
            errors.append(
                Warning(
                    "Vendored ALTCHA widget JS was not found by the staticfiles finders.",
                    id="altcha.W008",
                    hint="Run 'manage.py altcha_vendor_widget', or set ALTCHA_WIDGET_JS_SOURCE.",
                )
            )

    if conf.WIDGET_CHALLENGE_MODE == "endpoint":
        from django.urls import NoReverseMatch, reverse

        try:
            reverse("altcha_django:challenge")
        except NoReverseMatch:
            errors.append(
                Warning(
                    "ALTCHA_WIDGET_CHALLENGE_MODE='endpoint' but the challenge URL is not wired.",
                    id="altcha.W009",
                    hint="Add path('altcha/', include('altcha_django.urls')) to your URLconf.",
                )
            )

    if not conf.CHALLENGE_ENDPOINT_ENABLED:
        from django.urls import NoReverseMatch, reverse

        try:
            url = reverse("altcha_django:challenge")
        except NoReverseMatch:
            url = ""
        if url:
            errors.append(
                Warning(
                    "ALTCHA_CHALLENGE_ENDPOINT_ENABLED is False but the challenge URL is "
                    f"still wired at {url!r}, which now returns 404. Widgets pointed at it "
                    "cannot load a challenge.",
                    id="altcha.W015",
                    hint="Remove the altcha_django.urls include, or re-enable the endpoint.",
                )
            )

    errors.extend(_check_session_binding(cls))
    errors.extend(_check_widget_defaults())
    errors.extend(_check_trusted_proxies())

    if _is_sentinel(cls) and conf.SENTINEL_VERIFY_FIELDS:
        message = (
            "ALTCHA_SENTINEL_VERIFY_FIELDS is on; fieldsHash checks need "
            "AltchaMixin + AltchaField(bind_form_fields=[...]) on your forms."
        )
        if not conf.SENTINEL_SPAMFILTER:
            message += (
                " ALTCHA_SENTINEL_SPAMFILTER is off, so the widget does not send fields "
                "for classification: bound fields submitted non-empty will fail with "
                "fields_hash_mismatch unless the widget configuration sets verifyUrl."
            )
        errors.append(Info(message, id="altcha.W012"))

    for note in conf.deprecated_in_use():
        errors.append(Warning(note, id="altcha.W010"))
    for note, hint in conf.removed_in_use():
        errors.append(Error(note, id="altcha.E015", hint=hint))
    options = conf.VERIFIER_OPTIONS
    if _is_sentinel(cls) and isinstance(options, dict) and "min_score" in options:
        errors.append(
            Error(
                "ALTCHA_VERIFIER_OPTIONS['min_score'] was removed; SentinelVerifier refuses "
                "to start with it. It rejected Sentinel scores *below* the limit, but the "
                "score rises with spam likelihood.",
                id="altcha.E015",
                hint="Replace it with 'max_score' (GOOD < 1 <= NEUTRAL < 2 <= BAD); do not "
                "copy the old value, its meaning is inverted.",
            )
        )

    if (
        _is_sentinel(cls)
        and conf.SENTINEL_MODE == "remote"
        and conf.SENTINEL_RETRIES > 0
        and not conf.SENTINEL_HTTP_POST
    ):
        errors.append(
            Warning(
                "Sentinel remote mode with retries uses the stdlib urllib transport, "
                "which opens a new connection per attempt.",
                id="altcha.W011",
                hint="pip install 'altcha-django[sentinel]' and set ALTCHA_SENTINEL_HTTP_POST"
                " = 'altcha_django.transports.httpx_post'.",
            )
        )

    return errors


@register(_TAG, Tags.security, deploy=True)
def check_deploy(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    from django.conf import settings

    errors: list[CheckMessage] = []
    if conf.TEST_MODE and not settings.DEBUG:
        errors.append(
            Warning(
                "ALTCHA_TEST_MODE bypasses verification and DEBUG is False.",
                id="altcha.W004",
            )
        )
    return errors
