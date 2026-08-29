from __future__ import annotations

import json

import pytest
from altcha import Challenge, Payload, solve_challenge, verify_solution
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_challenge_view_returns_signed_challenge(client):
    resp = client.get("/altcha/challenge/")
    assert resp.status_code == 200
    assert resp["Cache-Control"] == "no-store"
    data = resp.json()
    assert set(data) == {"parameters", "signature"}
    # the issued challenge round-trips through verify_solution with the test secret
    challenge = Challenge.from_dict(data)
    payload = Payload(challenge, solve_challenge(challenge)).to_base64()
    assert verify_solution(payload, "test-hmac-secret").verified


def test_challenge_view_rejects_post(client):
    assert client.post("/altcha/challenge/").status_code == 405


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_ENABLED=False)
def test_challenge_view_can_be_disabled(client):
    assert client.get("/altcha/challenge/").status_code == 404


def allow_all(request):
    return True


def deny_all(request):
    return False


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT="tests.test_views.allow_all")
def test_ratelimit_hook_allows(client):
    assert client.get("/altcha/challenge/").status_code == 200


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT="tests.test_views.deny_all")
def test_ratelimit_blocks(client):
    resp = client.get("/altcha/challenge/")
    assert resp.status_code == 429
    assert resp["Retry-After"] == "60"


def test_simple_ip_ratelimit_gate():
    from django.test import RequestFactory

    from altcha_django.ratelimit import simple_ip_ratelimit

    gate = simple_ip_ratelimit("2/m")
    req = RequestFactory().get("/altcha/challenge/")
    assert gate(req) is True
    assert gate(req) is True
    assert gate(req) is False


@override_settings(ALTCHA_SENTINEL_PROXY_CHALLENGE=False)
def test_sentinel_proxy_disabled_by_default(client):
    assert client.get("/altcha/sentinel/challenge/").status_code == 404


def test_sentinel_proxy_when_enabled(client, settings):
    challenge_url = "https://sentinel.example.com/v1/challenge?apiKey=key_test"
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = challenge_url
    settings.ALTCHA_SENTINEL_API_SECRET = "secret"
    settings.ALTCHA_SENTINEL_PROXY_CHALLENGE = True

    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return 200, json.dumps({"parameters": {"algorithm": "SHA-256"}, "signature": "z"}).encode()

    from altcha_django.verifiers import get_verifier

    get_verifier("sentinel").http_get = fake_get

    resp = client.get("/altcha/sentinel/challenge/")
    assert resp.status_code == 200
    assert captured["url"] == challenge_url  # fetched verbatim, key in query string
    assert "Authorization" not in captured["headers"]


def test_sentinel_proxy_relays_widget_configuration(client, settings):
    """Sentinel configures the widget via `configuration` in the body; relay it intact."""
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = "https://sentinel.example.com/v1/challenge?apiKey=k"
    settings.ALTCHA_SENTINEL_API_SECRET = "secret"
    settings.ALTCHA_SENTINEL_PROXY_CHALLENGE = True

    upstream = {
        "parameters": {"algorithm": "SHA-256"},
        "signature": "z",
        "configuration": {"verifyUrl": "https://sentinel.example.com/v1/verify"},
        "codeChallenge": {"image": "data:image/png;base64,xx"},
    }

    def fake_get(url, headers, timeout):
        return 200, json.dumps(upstream).encode()

    from altcha_django.verifiers import get_verifier

    get_verifier("sentinel").http_get = fake_get

    resp = client.get("/altcha/sentinel/challenge/")
    assert resp.status_code == 200
    assert resp.json() == upstream  # every property survives the proxy


async def test_async_challenge_view(async_client):
    resp = await async_client.get("/altcha/async-challenge/")
    assert resp.status_code == 200
    assert set(resp.json()) == {"parameters", "signature"}


async def test_async_challenge_view_rejects_post(async_client):
    # Regression: the sync require_safe decorator used to make this raise
    # TypeError (awaiting a plain HttpResponseNotAllowed) instead of 405ing.
    resp = await async_client.post("/altcha/async-challenge/")
    assert resp.status_code == 405


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_ENABLED=False)
async def test_async_challenge_view_disabled(async_client):
    resp = await async_client.get("/altcha/async-challenge/")
    assert resp.status_code == 404


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT="tests.test_views.deny_all")
async def test_async_challenge_view_ratelimited(async_client):
    resp = await async_client.get("/altcha/async-challenge/")
    assert resp.status_code == 429


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True)
def test_challenge_view_session_binding(client):
    resp = client.get("/altcha/challenge/")
    token = resp.json()["parameters"]["data"]["id"]
    assert token in client.session["altcha_challenges"]


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True)
async def test_async_challenge_view_session_binding(async_client):
    resp = await async_client.get("/altcha/async-challenge/")
    assert "id" in resp.json()["parameters"]["data"]
