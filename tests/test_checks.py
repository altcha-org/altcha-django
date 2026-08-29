from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.checks import check_config, check_deploy

pytestmark = pytest.mark.django_db


def ids(messages):
    return {m.id for m in messages}


def test_clean_config_has_no_errors():
    msgs = check_config(None)
    assert not [m for m in msgs if m.id.startswith("altcha.E")]


@override_settings(ALTCHA_HMAC_SECRET=None)
def test_e003_missing_hmac_secret():
    assert "altcha.E003" in ids(check_config(None))


@override_settings(
    ALTCHA_VERIFIER="sentinel",
    ALTCHA_SENTINEL_CHALLENGE_URL=None,
    ALTCHA_SENTINEL_API_SECRET=None,
)
def test_sentinel_missing_url_and_secret():
    found = ids(check_config(None))
    assert "altcha.E005" in found  # missing challenge URL
    assert "altcha.E004" in found  # missing API secret (local mode)


@override_settings(
    ALTCHA_VERIFIER="sentinel",
    ALTCHA_SENTINEL_CHALLENGE_URL="sentinel.example.com/v1/challenge",  # not absolute
    ALTCHA_SENTINEL_API_SECRET="sec",
)
def test_e005_non_absolute_challenge_url():
    assert "altcha.E005" in ids(check_config(None))


@override_settings(
    ALTCHA_VERIFIER="sentinel",
    ALTCHA_SENTINEL_CHALLENGE_URL="https://sentinel.example.com/v1/challenge?apiKey=k",
    ALTCHA_SENTINEL_API_SECRET="sec",
)
def test_sentinel_valid_config_has_no_errors():
    assert not [m for m in check_config(None) if m.id.startswith("altcha.E")]


@override_settings(ALTCHA_VERIFIER="tests.does.not.Exist")
def test_e002_bad_verifier():
    assert "altcha.E002" in ids(check_config(None))


@override_settings(ALTCHA_CACHE_ALIAS="missing")
def test_e007_unknown_cache_alias():
    assert "altcha.E007" in ids(check_config(None))


@override_settings(ALTCHA_WIDGET_JS_SOURCE="custom", ALTCHA_WIDGET_JS_URL=None)
def test_e008_custom_source_without_url():
    assert "altcha.E008" in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE={"algorithm": "ROT13", "cost": 5000})
def test_e009_unknown_algorithm():
    assert "altcha.E009" in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE={"key_prefix": "zzz"})
def test_e010_non_hex_key_prefix():
    assert "altcha.E010" in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE={"key_prefix": "zzz", "max_number": 10000})
def test_e010_not_raised_in_deterministic_mode():
    assert "altcha.E010" not in ids(check_config(None))


def test_w001_locmem_replay_warning():
    assert "altcha.W001" in ids(check_config(None))


@override_settings(ALTCHA_CACHE_ALIAS="dummy")
def test_w002_dummy_cache():
    assert "altcha.W002" in ids(check_config(None))


@override_settings(ALTCHA_REPLAY_PROTECTION=False)
def test_w003_replay_disabled():
    assert "altcha.W003" in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE={"algorithm": "PBKDF2/SHA-256", "cost": 10})
def test_w006_low_cost():
    assert "altcha.W006" in ids(check_config(None))


@override_settings(
    ALTCHA_CHALLENGE={"algorithm": "PBKDF2/SHA-256", "cost": 5000, "expires_seconds": 5}
)
def test_w007_short_expiry():
    assert "altcha.W007" in ids(check_config(None))


@override_settings(DEBUG=False, ALTCHA_TEST_MODE=True)
def test_w004_test_mode_deploy_warning():
    assert "altcha.W004" in ids(check_deploy(None))


@override_settings(ALTCHA_HMAC_KEY="legacy-value")
def test_w010_deprecated_setting():
    assert "altcha.W010" in ids(check_config(None))


@override_settings(ALTCHA_WIDGET_CHALLENGE_MODE="endpoint")
def test_w009_only_when_url_missing():
    # tests.urls DOES wire the endpoint, so W009 must NOT fire here
    assert "altcha.W009" not in ids(check_config(None))


# --- session binding (E006 / E011 / W013) -------------------------------
def test_no_session_binding_checks_when_feature_is_off():
    found = ids(check_config(None))
    assert {"altcha.E006", "altcha.E011", "altcha.W013"}.isdisjoint(found)


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True)
def test_bind_session_is_clean_with_endpoint_and_sessions():
    # tests.settings has sessions + middleware, tests.urls wires the endpoint
    found = ids(check_config(None))
    assert {"altcha.E006", "altcha.E011", "altcha.W013"}.isdisjoint(found)


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True, ALTCHA_WIDGET_CHALLENGE_MODE="inline")
def test_e006_bind_session_with_inline_challenges():
    assert "altcha.E006" in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True)
def test_e006_bind_session_without_wired_urls():
    from django.urls import set_urlconf

    set_urlconf("tests.urls_empty")
    try:
        assert "altcha.E006" in ids(check_config(None))
    finally:
        set_urlconf(None)


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True, MIDDLEWARE=[])
def test_e011_bind_session_without_session_middleware():
    assert "altcha.E011" in ids(check_config(None))


@override_settings(
    ALTCHA_CHALLENGE_BIND_SESSION=True,
    ALTCHA_VERIFIER="sentinel",
    ALTCHA_SENTINEL_CHALLENGE_URL="https://sentinel.example.com/v1/challenge?apiKey=k",
    ALTCHA_SENTINEL_API_SECRET="sec",
)
def test_w013_bind_session_has_no_effect_on_sentinel():
    found = ids(check_config(None))
    assert "altcha.W013" in found
    assert "altcha.E006" not in found  # the endpoint requirement is local-only


@override_settings(ALTCHA_CHALLENGE_BIND_SESSION=True, ALTCHA_VERIFIER="null")
def test_w013_bind_session_has_no_effect_on_null_verifier():
    assert "altcha.W013" in ids(check_config(None))


# --- ALTCHA_WIDGET_DEFAULTS key validation (W014) ------------------------
def test_w014_not_raised_for_valid_defaults():
    assert "altcha.W014" not in ids(check_config(None))


@override_settings(ALTCHA_WIDGET_DEFAULTS={"hideLogo": True, "minDuration": 1000})
def test_w014_reports_configuration_keys_put_in_defaults():
    msg = next(m for m in check_config(None) if m.id == "altcha.W014")
    assert "hideLogo" in msg.msg and "minDuration" in msg.msg
    assert "ALTCHA_WIDGET_CONFIGURATION" in msg.hint


@override_settings(ALTCHA_WIDGET_DEFAULTS={"name": "captcha"})
def test_w014_calls_out_widget_managed_attributes():
    msg = next(m for m in check_config(None) if m.id == "altcha.W014")
    assert "set by altcha-django itself" in msg.hint


@override_settings(ALTCHA_WIDGET_DEFAULTS={"type": "switch", "theme": "dark"})
def test_w014_accepts_every_real_element_attribute():
    from altcha_django.widgets import ELEMENT_ATTRS

    assert set(ELEMENT_ATTRS) >= {"type", "theme"}
    assert "altcha.W014" not in ids(check_config(None))


# --- endpoint disabled but still routed (W015) ---------------------------
def test_w015_not_raised_when_endpoint_is_enabled():
    assert "altcha.W015" not in ids(check_config(None))


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_ENABLED=False)
def test_w015_endpoint_disabled_while_urls_are_wired():
    # tests.urls includes altcha_django.urls, so the route now 404s
    msg = next(m for m in check_config(None) if m.id == "altcha.W015")
    assert "/altcha/challenge/" in msg.msg


@override_settings(ALTCHA_CHALLENGE_ENDPOINT_ENABLED=False)
def test_w015_silent_when_urls_are_not_wired():
    from django.urls import set_urlconf

    set_urlconf("tests.urls_empty")
    try:
        assert "altcha.W015" not in ids(check_config(None))
    finally:
        set_urlconf(None)
