"""The shipped httpx transports (``altcha-django[sentinel]``)."""

from __future__ import annotations

import os

import pytest
from django.test import override_settings

from altcha_django.verifiers.sentinel import SentinelVerifier, _resolve_callable

httpx = pytest.importorskip("httpx")

from altcha_django import transports  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client():
    """Never leak a client (or a mocked one) between tests."""
    transports.close_client()
    yield
    transports.close_client()


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_httpx_post_returns_status_and_body(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content
        seen["ct"] = request.headers.get("content-type")
        return httpx.Response(200, json={"verified": True})

    monkeypatch.setattr(transports, "get_client", lambda: _mock_client(handler))
    status, body = transports.httpx_post(
        "https://s.example.com/v1/verify/signature",
        b'{"payload": "p"}',
        {"Content-Type": "application/json"},
        5.0,
    )
    assert status == 200
    assert b'"verified"' in body
    assert seen["url"] == "https://s.example.com/v1/verify/signature"
    assert seen["body"] == b'{"payload": "p"}'
    assert seen["ct"] == "application/json"


def test_httpx_post_reports_error_status_without_raising(monkeypatch):
    monkeypatch.setattr(
        transports, "get_client", lambda: _mock_client(lambda r: httpx.Response(400, text="nope"))
    )
    status, body = transports.httpx_post("https://s.example.com/v", b"{}", {}, 1.0)
    assert (status, body) == (400, b"nope")


def test_httpx_get_returns_status_and_body(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"parameters": {}, "signature": "s"})

    monkeypatch.setattr(transports, "get_client", lambda: _mock_client(handler))
    status, body = transports.httpx_get("https://s.example.com/v1/challenge", {}, 5.0)
    assert status == 200
    assert b"signature" in body


def test_httpx_get_drives_the_sentinel_challenge_proxy(monkeypatch, client, settings):
    """The shipped transport satisfies the contract the proxy view relies on."""
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = "https://s.example.com/v1/challenge?apiKey=k"
    settings.ALTCHA_SENTINEL_API_SECRET = "sec"
    settings.ALTCHA_SENTINEL_PROXY_CHALLENGE = True
    settings.ALTCHA_SENTINEL_HTTP_GET = "altcha_django.transports.httpx_get"

    upstream = {"parameters": {}, "signature": "s", "configuration": {"hideLogo": True}}
    monkeypatch.setattr(
        transports,
        "get_client",
        lambda: _mock_client(lambda r: httpx.Response(200, json=upstream)),
    )

    resp = client.get("/altcha/sentinel/challenge/")
    assert resp.status_code == 200
    assert resp.json() == upstream


# --- client lifecycle ---------------------------------------------------
def test_get_client_is_cached():
    assert transports.get_client() is transports.get_client()


def test_client_is_rebuilt_after_a_fork(monkeypatch):
    first = transports.get_client()
    child_pid = os.getpid() + 1
    monkeypatch.setattr(os, "getpid", lambda: child_pid)
    second = transports.get_client()
    assert second is not first  # a forked child must not reuse the parent's sockets
    assert not first.is_closed  # ... and must not close the parent's sockets either


def test_close_client_is_idempotent():
    transports.get_client()
    transports.close_client()
    transports.close_client()


# --- settings wiring ----------------------------------------------------
def test_settings_accept_dotted_paths():
    with override_settings(
        ALTCHA_SENTINEL_CHALLENGE_URL="https://s.example.com/v1/challenge?apiKey=k",
        ALTCHA_SENTINEL_API_SECRET="sec",
        ALTCHA_SENTINEL_HTTP_POST="altcha_django.transports.httpx_post",
        ALTCHA_SENTINEL_HTTP_GET="altcha_django.transports.httpx_get",
    ):
        v = SentinelVerifier()
        assert v.http_post is transports.httpx_post
        assert v.http_get is transports.httpx_get


def test_resolve_callable_passes_through_callables_and_none():
    assert _resolve_callable(None) is None
    assert _resolve_callable(transports.httpx_post) is transports.httpx_post
