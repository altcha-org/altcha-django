"""Single-use enforcement for solved challenges, backed by Django's cache."""

from __future__ import annotations

import hashlib
import time

from django.core.cache import caches

from .conf import conf


class ReplayProtector:
    """Records accepted payloads so the same solution can't be reused.

    The claim is atomic: :meth:`register` uses ``cache.add`` (compare-and-set), so
    concurrent requests replaying one payload cannot both succeed.
    """

    def __init__(
        self,
        *,
        cache_alias: str | None = None,
        key_prefix: str | None = None,
        fallback_ttl: int | None = None,
        clock_skew: int | None = None,
    ) -> None:
        self.cache = caches[cache_alias or conf.CACHE_ALIAS]
        self.key_prefix = key_prefix or conf.REPLAY_KEY_PREFIX
        self.fallback_ttl = fallback_ttl if fallback_ttl is not None else conf.REPLAY_FALLBACK_TTL
        self.clock_skew = clock_skew if clock_skew is not None else conf.REPLAY_CLOCK_SKEW

    def _key(self, replay_id: str, scope: str) -> str:
        digest = hashlib.sha256(f"{scope}:{replay_id}".encode()).hexdigest()
        return f"{self.key_prefix}{digest}"

    def _ttl(self, expires_at: int | None) -> int:
        if expires_at:
            remaining = int(expires_at) - int(time.time()) + self.clock_skew
            return max(1, remaining)
        return self.fallback_ttl

    def register(self, replay_id: str, *, expires_at: int | None = None, scope: str = "") -> bool:
        """Claim ``replay_id``. Returns ``True`` on first use, ``False`` if already seen."""
        return bool(self.cache.add(self._key(replay_id, scope), 1, timeout=self._ttl(expires_at)))

    def seen(self, replay_id: str, *, scope: str = "") -> bool:
        return self.cache.get(self._key(replay_id, scope)) is not None
