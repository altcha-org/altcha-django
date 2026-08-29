"""Optional httpx transports for the Sentinel backend.

The stdlib ``urllib`` transports the verifier falls back on open a fresh
connection per call, which is wasteful when every form submission in remote mode
POSTs to Sentinel (and costs an extra round-trip on each retry). These
drop-in replacements reuse one pooled, thread-safe :class:`httpx.Client`.

Requires ``pip install 'altcha-django[sentinel]'``::

    ALTCHA_SENTINEL_HTTP_POST = "altcha_django.transports.httpx_post"
    ALTCHA_SENTINEL_HTTP_GET = "altcha_django.transports.httpx_get"

``HTTP_POST`` is used to verify payloads in ``mode="remote"``; ``HTTP_GET``
fetches challenges when ``ALTCHA_SENTINEL_PROXY_CHALLENGE`` is on. Both callables
match the signatures the verifier and ``altcha.verify_server`` expect, so they can
also be passed straight to ``SentinelVerifier(...)``.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

_client: httpx.Client | None = None
_client_pid: int | None = None
_lock = threading.Lock()


def _import_httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "altcha_django.transports requires httpx. "
            "Install with: pip install 'altcha-django[sentinel]'"
        ) from exc
    return httpx


def get_client() -> httpx.Client:
    """Return the shared :class:`httpx.Client`, creating it on first use.

    Created lazily rather than at import time so that a process forked by
    gunicorn/uWSGI never inherits a parent's sockets; the owning PID is recorded
    and the client rebuilt if it is ever seen from a different process.
    """
    global _client, _client_pid

    pid = os.getpid()
    if _client is not None and _client_pid == pid:
        return _client

    with _lock:
        if _client is None or _client_pid != pid:
            httpx = _import_httpx()
            # A client inherited across a fork is unusable; drop it without
            # closing (the sockets belong to the parent).
            _client = httpx.Client(follow_redirects=False)
            _client_pid = pid
    return _client


def close_client() -> None:
    """Close the shared client, if one was created. Safe to call repeatedly."""
    global _client, _client_pid

    with _lock:
        if _client is not None and _client_pid == os.getpid():
            _client.close()
        _client = None
        _client_pid = None


def httpx_post(
    url: str, data: bytes, headers: dict[str, str], timeout: float
) -> tuple[int, bytes]:
    """POST transport for ``ALTCHA_SENTINEL_HTTP_POST``.

    Returns ``(status, body)`` for any HTTP status; network failures raise, which
    is what ``altcha.verify_server`` expects — it catches them to drive retries.
    """
    response = get_client().post(url, content=data, headers=headers, timeout=timeout)
    return response.status_code, response.content


def httpx_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    """GET transport for ``ALTCHA_SENTINEL_HTTP_GET``.

    Returns ``(status, body)`` for any HTTP status; network failures raise.
    """
    response = get_client().get(url, headers=headers, timeout=timeout)
    return response.status_code, response.content
