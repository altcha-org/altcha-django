"""Client-IP resolution and a tiny cache-backed rate limiter for the challenge endpoint.

The limiter is intentionally minimal. For anything serious use a dedicated package
(``django-ratelimit``) and point ``ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT`` at it —
:func:`client_ip` is public so your own gate can reuse the same trusted-proxy logic.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache

from django.core.cache import caches
from django.http import HttpRequest

from .conf import conf

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=8)
def _networks(values: tuple[str, ...]) -> tuple[_Network, ...]:
    """Parse ``ALTCHA_TRUSTED_PROXIES`` into networks, dropping unparseable entries.

    A malformed entry simply never matches, so the header stays untrusted (fail
    closed); ``checks.E012`` reports it rather than failing a request.
    """
    parsed: list[_Network] = []
    for value in values:
        try:
            parsed.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(parsed)


def _trusted(ip: str, networks: Sequence[_Network]) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def client_ip(request: HttpRequest, *, trusted_proxies: Iterable[str] | None = None) -> str:
    """Return the client's IP address, honouring ``X-Forwarded-For`` only when safe.

    ``X-Forwarded-For`` is attacker-controlled: any client can send one. It is
    therefore consulted **only** when ``ALTCHA_TRUSTED_PROXIES`` says the request
    reached us through a known proxy. The chain is then walked right-to-left
    (nearest hop first) and the first address that is not itself a trusted proxy
    is the client — so a forged prefix cannot be used to impersonate anyone or to
    mint unlimited rate-limit buckets.

    With no trusted proxies configured (the default) the header is ignored
    entirely and ``REMOTE_ADDR`` is used.
    """
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    values = conf.TRUSTED_PROXIES if trusted_proxies is None else trusted_proxies
    networks = _networks(tuple(str(v) for v in values))

    # No configured proxies, or the peer is not one of them -> the header is
    # unverifiable; only the socket address can be believed.
    if not networks or not _trusted(remote, networks):
        return remote or "unknown"

    chain = [
        part.strip()
        for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if part.strip()
    ]
    for candidate in reversed(chain):
        if not _trusted(candidate, networks):
            return candidate
    # Every hop is our own infrastructure: nothing more specific than the peer.
    return remote or "unknown"


def simple_ip_ratelimit(rate: str = "60/m") -> Callable[[HttpRequest], bool]:
    """Return a ``(request) -> bool`` gate. ``rate`` is ``"<count>/<s|m|h>"``."""
    count_str, _, period = rate.partition("/")
    limit = int(count_str)
    window = {"s": 1, "m": 60, "h": 3600}[period[:1] or "m"]

    def gate(request: HttpRequest) -> bool:
        cache = caches[conf.CACHE_ALIAS]
        bucket = int(time.time()) // window
        key = f"altcha:rl:{bucket}:{client_ip(request)}"
        try:
            cache.add(key, 0, timeout=window + 5)
            current = int(cache.incr(key))
        except ValueError:
            current = int(cache.get_or_set(key, 1, timeout=window + 5) or 1)
        return current <= limit

    return gate
