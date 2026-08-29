"""Targeted tests for small branches not exercised elsewhere."""

from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings

from altcha_django.challenge import ChallengeConfig, build_challenge, challenge_to_dict
from altcha_django.exceptions import AltchaConfigurationError

pytestmark = pytest.mark.django_db


# --- challenge ----------------------------------------------------------------
def test_challenge_config_validate_errors():
    with pytest.raises(AltchaConfigurationError):
        ChallengeConfig(cost=0).validate()
    with pytest.raises(AltchaConfigurationError):
        ChallengeConfig(expires_seconds=0).validate()


def test_challenge_to_dict_helper():
    data = challenge_to_dict(build_challenge(hmac_secret="s"))
    assert set(data) == {"parameters", "signature"}


# --- forms ------------------------------------------------------------------
def test_field_to_python_and_not_required():
    from altcha_django.forms import AltchaField

    field = AltchaField(required=False)
    assert field.clean("") == ""
    assert field.to_python(None) == ""
    assert field.to_python(" abc ") == " abc "


# --- widgets --------------------------------------------------------------
def test_module_script_str_and_notimplemented():
    from altcha_django.widgets import ModuleScript

    assert str(ModuleScript("/x")) == "/x"
    assert ModuleScript("/x").__eq__(42) is NotImplemented


# --- base verifier --------------------------------------------------------
def test_base_verify_not_implemented():
    from altcha_django.verifiers.base import BaseVerifier

    with pytest.raises(NotImplementedError):
        BaseVerifier().verify("x")


# --- views --------------------------------------------------------------
def test_client_challenge_bind_without_token_is_noop():
    from altcha_django.views import _client_challenge_bind

    request = RequestFactory().get("/")
    request.session = {}
    _client_challenge_bind(request, {"parameters": {}})  # no data.id
    assert request.session == {}


# --- ratelimit ---------------------------------------------------------
def test_forwarded_for_is_ignored_without_trusted_proxies():
    """The header is attacker-controlled; by default only REMOTE_ADDR is believed."""
    from altcha_django.ratelimit import client_ip

    req = RequestFactory().get(
        "/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", REMOTE_ADDR="10.0.0.9"
    )
    assert client_ip(req) == "10.0.0.9"


@override_settings(ALTCHA_CACHE_ALIAS="dummy")
def test_ratelimit_gate_survives_dummy_cache():
    from altcha_django.ratelimit import simple_ip_ratelimit

    gate = simple_ip_ratelimit("1/s")
    # DummyCache: incr raises ValueError -> gate falls back to get_or_set path
    assert gate(RequestFactory().get("/")) in (True, False)


# --- sentinel misc -------------------------------------------------------
def test_sentinel_http_post_dotted_path(settings):
    settings.ALTCHA_SENTINEL_HTTP_POST = "tests.test_misc_coverage.fake_post_marker"
    from altcha_django.verifiers.sentinel import SentinelVerifier

    v = SentinelVerifier(
        challenge_url="https://s.example.com/v1/challenge?apiKey=k", api_secret="s"
    )
    assert v.http_post is fake_post_marker


def fake_post_marker(url, data, headers, timeout):  # referenced by dotted path above
    return 200, b"{}"


def test_default_http_get_handles_http_error(monkeypatch):
    import urllib.error

    from altcha_django.verifiers.sentinel import _default_http_get

    class _Err(urllib.error.HTTPError):
        def __init__(self):
            pass

        code = 503

        def read(self):
            return b"boom"

    def raise_err(*a, **k):
        raise _Err()

    monkeypatch.setattr("urllib.request.urlopen", raise_err)
    status, body = _default_http_get("https://x/y", {}, 1.0)
    assert status == 503 and body == b"boom"


# --- checks: W011 + clean deploy ---------------------------------------
@override_settings(
    ALTCHA_VERIFIER="sentinel",
    ALTCHA_SENTINEL_CHALLENGE_URL="https://s.example.com/v1/challenge?apiKey=k",
    ALTCHA_SENTINEL_API_SECRET="s",
    ALTCHA_SENTINEL_MODE="remote",
    ALTCHA_SENTINEL_RETRIES=2,
)
def test_check_w011_remote_retries_default_transport():
    from altcha_django.checks import check_config

    assert "altcha.W011" in {m.id for m in check_config(None)}


def test_check_deploy_clean():
    from altcha_django.checks import check_deploy

    assert check_deploy(None) == []


@override_settings(ALTCHA_CHALLENGE={"algorithm": "ARGON2ID", "cost": 3})
def test_check_w005_argon2_missing(monkeypatch):
    import builtins

    from altcha_django.checks import check_config

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "argon2":
            raise ImportError("no argon2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert "altcha.W005" in {m.id for m in check_config(None)}
