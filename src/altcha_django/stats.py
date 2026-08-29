"""Opt-in, best-effort verification counters kept in the cache.

Enable with ``ALTCHA_COLLECT_STATS = True``. Counters are approximate (cache
backends make no strong atomicity or durability guarantees); wire your own signal
receiver for real analytics.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import caches

from .conf import conf
from .results import VerificationResult
from .signals import altcha_verification_failed, altcha_verified

PREFIX = "altcha:stats:"
WINDOW = 86_400


class CacheStatsRecorder:
    _DISPATCH_OK = "altcha-django-stats-ok"
    _DISPATCH_FAIL = "altcha-django-stats-fail"

    def connect(self) -> None:
        altcha_verified.connect(self._on_ok, dispatch_uid=self._DISPATCH_OK)
        altcha_verification_failed.connect(self._on_fail, dispatch_uid=self._DISPATCH_FAIL)

    def disconnect(self) -> None:
        altcha_verified.disconnect(dispatch_uid=self._DISPATCH_OK)
        altcha_verification_failed.disconnect(dispatch_uid=self._DISPATCH_FAIL)

    # -- receivers ----------------------------------------------------
    def _on_ok(self, sender: Any, *, result: VerificationResult, **_kw: Any) -> None:
        self._incr(f"{PREFIX}ok:{result.payload_type}")
        self._incr(f"{PREFIX}ok:total")

    def _on_fail(self, sender: Any, *, code: str | None = None, **_kw: Any) -> None:
        self._incr(f"{PREFIX}fail:{code or 'unknown'}")
        self._incr(f"{PREFIX}fail:total")

    # -- helpers ----------------------------------------------------
    def _incr(self, key: str) -> None:
        cache = caches[conf.CACHE_ALIAS]
        try:
            cache.add(key, 0, timeout=WINDOW)
            cache.incr(key)
        except ValueError:  # pragma: no cover - race with expiry
            cache.set(key, 1, timeout=WINDOW)

    def snapshot(self) -> dict[str, int]:
        """Return the current counters as a plain dict (for a health/status page)."""
        cache = caches[conf.CACHE_ALIAS]
        keys = [
            f"{PREFIX}ok:total",
            f"{PREFIX}fail:total",
            *[
                f"{PREFIX}ok:{name}"
                for name in ("pow_v2", "server_signature", "sentinel_remote", "test")
            ],
        ]
        return {k.removeprefix(PREFIX): v for k, v in cache.get_many(keys).items()}


recorder = CacheStatsRecorder()
