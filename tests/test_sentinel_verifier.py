from __future__ import annotations

import json

import pytest

from altcha_django.exceptions import AltchaConfigurationError
from altcha_django.results import ErrorCode, PayloadType
from altcha_django.verifiers.sentinel import SentinelVerifier
from tests import factories

pytestmark = pytest.mark.django_db

SECRET = "sentinel-secret"
CHALLENGE_URL = "https://sentinel.example.com/v1/challenge?apiKey=key_test"


def make_verifier(**kw):
    kw.setdefault("challenge_url", CHALLENGE_URL)
    kw.setdefault("api_secret", SECRET)
    kw.setdefault("verify_fields", False)
    return SentinelVerifier(**kw)


# --- local mode ------------------------------------------------------------
def test_local_valid():
    result = make_verifier().verify(factories.make_sentinel_payload(SECRET))
    assert result.verified
    assert result.payload_type == PayloadType.SERVER_SIGNATURE
    assert result.classification == "GOOD"
    assert result.replay_id


def test_local_bad_signature():
    payload = factories.make_sentinel_payload(SECRET, bad_signature=True)
    assert make_verifier().verify(payload).code == ErrorCode.INVALID_SIGNATURE.value


def test_local_expired():
    payload = factories.make_sentinel_payload(SECRET, expire_in=-10)
    assert make_verifier().verify(payload).code == ErrorCode.EXPIRED.value


def test_classification_bad_rejected():
    payload = factories.make_sentinel_payload(SECRET, classification="BAD")
    result = make_verifier().verify(payload)
    assert result.code == ErrorCode.CLASSIFICATION_REJECTED.value
    assert result.classification == "BAD"


def test_score_threshold():
    payload = factories.make_sentinel_payload(SECRET, score=0.2)
    result = make_verifier(min_score=0.5).verify(payload)
    assert result.code == ErrorCode.SCORE_REJECTED.value


def test_fields_hash_match():
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}
    )
    result = make_verifier(verify_fields=True).verify(payload, form_data={"email": "a@b.com"})
    assert result.verified


def test_fields_hash_mismatch():
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}
    )
    result = make_verifier(verify_fields=True).verify(payload, form_data={"email": "evil@x.com"})
    assert result.code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_fields_hash_without_form_data():
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}
    )
    result = make_verifier(verify_fields=True).verify(payload)
    assert result.code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_local_missing_secret():
    result = make_verifier(api_secret=None).verify(factories.make_sentinel_payload(SECRET))
    assert result.code == ErrorCode.MISCONFIGURED.value


def test_pow_payload_rejected_by_sentinel():
    result = make_verifier().verify(factories.make_pow_payload("x"))
    assert result.code == ErrorCode.MALFORMED.value


# --- remote mode -----------------------------------------------------------
def _fake_post(response: dict, status: int = 200):
    def post(url, data, headers, timeout):
        return status, json.dumps(response).encode()

    return post


def test_remote_verified():
    v = make_verifier(
        mode="remote",
        http_post=_fake_post(
            {
                "verified": True,
                "verificationData": "verified=true&score=0&classification=GOOD&expire=99999999999&id=abc",
            }
        ),
    )
    result = v.verify(factories.make_sentinel_payload(SECRET))
    assert result.verified
    assert result.payload_type == PayloadType.SENTINEL_REMOTE


def test_remote_replay():
    v = make_verifier(
        mode="remote",
        http_post=_fake_post(
            {"verified": False, "reason": "PAYLOAD_ALREADY_USED", "apiKey": None}
        ),
    )
    result = v.verify(factories.make_sentinel_payload(SECRET))
    assert result.code == ErrorCode.REPLAYED.value


def test_remote_transport_error():
    def boom(url, data, headers, timeout):
        raise OSError("connection refused")

    v = make_verifier(mode="remote", http_post=boom)
    result = v.verify(factories.make_sentinel_payload(SECRET))
    assert result.code == ErrorCode.BACKEND_ERROR.value


# --- config --------------------------------------------------------------
def test_widget_challenge_ref_is_the_full_url():
    assert make_verifier().get_widget_challenge_ref() == CHALLENGE_URL


def test_verify_url_is_derived_from_challenge_url():
    assert make_verifier().verify_url == "https://sentinel.example.com/v1/verify/signature"
    assert make_verifier().widget_verify_url == "https://sentinel.example.com/v1/verify"


def test_verify_url_can_be_overridden():
    v = make_verifier(verify_url="https://other.example.com/verify")
    assert v.verify_url == "https://other.example.com/verify"


def test_verify_url_derivation_fails_for_weird_challenge_url():
    v = make_verifier(challenge_url="https://sentinel.example.com/get-a-challenge")
    with pytest.raises(AltchaConfigurationError):
        _ = v.verify_url


def test_widget_challenge_ref_uses_proxy_when_enabled():
    ref = make_verifier(proxy_challenge=True).get_widget_challenge_ref()
    assert ref == "/altcha/sentinel/challenge/"


def test_get_challenge_fetches_the_full_url_verbatim():
    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return 200, b'{"parameters": {"x": 1}, "signature": "s"}'

    v = make_verifier(http_get=fake_get)
    challenge = v.get_challenge()
    assert challenge == {"parameters": {"x": 1}, "signature": "s"}
    assert captured["url"] == CHALLENGE_URL  # api key in the query string, no auth header
    assert "Authorization" not in captured["headers"]


def test_get_challenge_without_url_raises():
    with pytest.raises(AltchaConfigurationError):
        SentinelVerifier(challenge_url=None, api_secret=SECRET).get_challenge()


def test_get_challenge_returns_the_configuration_property_verbatim():
    """Sentinel configures the widget through `configuration` in the challenge JSON."""

    def fake_get(url, headers, timeout):
        return 200, b'{"parameters": {}, "signature": "s", "configuration": {"hideLogo": true}}'

    challenge = make_verifier(http_get=fake_get).get_challenge()
    assert challenge["configuration"] == {"hideLogo": True}


def test_garbage_payload_rejected():
    assert make_verifier().verify("not-base64!!").code == ErrorCode.MALFORMED.value


def test_empty_payload_required():
    assert make_verifier().verify("").code == ErrorCode.REQUIRED.value


def test_remote_verdict_without_data_is_backend_error():
    v = make_verifier(
        mode="remote", http_post=_fake_post({"verified": False, "reason": "HTTP_503"}, status=503)
    )
    assert v.verify(factories.make_sentinel_payload(SECRET)).code == ErrorCode.BACKEND_ERROR.value


def test_remote_verdict_with_data_is_unverified():
    body = {
        "verified": False,
        "reason": "SPAM",
        "verificationData": {"verified": False, "classification": "BAD", "score": 3},
    }
    v = make_verifier(mode="remote", http_post=_fake_post(body))
    assert v.verify(factories.make_sentinel_payload(SECRET)).code == ErrorCode.UNVERIFIED.value


# --- fieldsHash digest follows the payload -------------------------------
def test_fields_hash_uses_the_algorithm_named_by_the_payload():
    """Sentinel names its digest in the payload; SHA-512 must verify as SHA-512."""
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}, algorithm="SHA-512"
    )
    result = make_verifier(verify_fields=True).verify(payload, form_data={"email": "a@b.com"})
    assert result.verified, result.error


def test_fields_hash_mismatch_under_a_non_default_algorithm():
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}, algorithm="SHA-512"
    )
    result = make_verifier(verify_fields=True).verify(payload, form_data={"email": "evil@x.com"})
    assert not result.verified
    assert result.code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_hostile_payload_algorithm_is_rejected_not_raised():
    """The payload names its own digest; an unknown one must not reach hashlib.new()."""
    import base64
    import json

    evil = base64.b64encode(
        json.dumps(
            {
                "algorithm": "../../etc/passwd",
                "signature": "00",
                "verificationData": "verified=true",
                "verified": True,
            }
        ).encode()
    ).decode()
    result = make_verifier().verify(evil)  # must not raise
    assert not result.verified
    assert result.code == ErrorCode.MALFORMED.value
