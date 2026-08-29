from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.conf import conf

pytestmark = pytest.mark.django_db


def test_unknown_setting_raises():
    with pytest.raises(AttributeError):
        conf.NOT_A_REAL_SETTING  # noqa: B018


def test_challenge_dict_is_merged_not_replaced():
    with override_settings(ALTCHA_CHALLENGE={"cost": 999}):
        assert conf.CHALLENGE["cost"] == 999
        assert conf.CHALLENGE["algorithm"] == "PBKDF2/SHA-256"  # from defaults


def test_widget_defaults_merged():
    with override_settings(ALTCHA_WIDGET_DEFAULTS={"type": "switch"}):
        assert conf.WIDGET_DEFAULTS["type"] == "switch"
        assert conf.WIDGET_DEFAULTS["display"] == "standard"


@override_settings(ALTCHA_HMAC_KEY="legacy-secret", ALTCHA_HMAC_SECRET=None)
def test_deprecated_hmac_key_is_honoured():
    assert conf.HMAC_SECRET == "legacy-secret"
    assert any("ALTCHA_HMAC_KEY" in n for n in conf.deprecated_in_use())


@override_settings(ALTCHA_VERIFICATION_ENABLED=False)
def test_legacy_verification_disabled_maps_to_null():
    assert conf.VERIFIER == "null"
    assert any("ALTCHA_VERIFICATION_ENABLED" in n for n in conf.deprecated_in_use())


@override_settings(ALTCHA_JS_URL="/legacy/altcha.js", ALTCHA_WIDGET_JS_URL=None)
def test_legacy_js_url_implies_custom_source():
    assert conf.WIDGET_JS_SOURCE == "custom"
    assert conf.WIDGET_JS_URL == "/legacy/altcha.js"


@override_settings(
    ALTCHA_SENTINEL_CHALLENGE_URL="https://sentinel.example.com/v1/challenge?apiKey=k"
)
def test_sentinel_challenge_url_setting():
    assert conf.SENTINEL_CHALLENGE_URL.endswith("apiKey=k")
    assert conf.SENTINEL_VERIFY_URL is None  # derived at use time, not stored


def test_setting_changed_clears_cache():
    first = conf.HMAC_SECRET
    with override_settings(ALTCHA_HMAC_SECRET="changed"):
        assert conf.HMAC_SECRET == "changed"
    assert conf.HMAC_SECRET == first


# --- memory_cost -----------------------------------------------------------
def test_memory_cost_is_the_default_key():
    assert "memory_cost" in conf.CHALLENGE
    assert "max_memory" not in conf.CHALLENGE


@override_settings(ALTCHA_CHALLENGE={"memory_cost": 65536})
def test_memory_cost_setting():
    assert conf.CHALLENGE["memory_cost"] == 65536
