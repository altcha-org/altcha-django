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


@pytest.mark.parametrize(
    ("score", "verified"),
    [(0, True), (0.2, True), (1.5, True), ("1.5", True), (1.6, False), (5, False)],
)
def test_max_score_rejects_spammy_scores(score, verified):
    """Sentinel's score rises with spam likelihood (GOOD < 1 <= NEUTRAL < 2 <= BAD)."""
    payload = factories.make_sentinel_payload(SECRET, score=score)
    result = make_verifier(max_score=1.5, reject_classifications=[]).verify(payload)
    assert result.verified is verified
    if not verified:
        assert result.code == ErrorCode.SCORE_REJECTED.value


@pytest.mark.parametrize("score", ["1e-7", "-1"])
def test_score_in_other_number_formats_is_parsed(score):
    """parse_verification_data leaves these as text; they are still numbers."""
    payload = factories.make_sentinel_payload(SECRET, score=score)
    result = make_verifier(max_score=0.5).verify(payload)
    assert result.verified
    assert result.score == float(score)


@pytest.mark.parametrize("score", ["high", "nan", "inf", ""])
def test_unparseable_score_is_rejected_when_limited(score):
    payload = factories.make_sentinel_payload(SECRET, score=score)
    result = make_verifier(max_score=0.5).verify(payload)
    assert result.code == ErrorCode.SCORE_REJECTED.value
    assert make_verifier().verify(payload).verified  # no limit: score is informational


@pytest.mark.parametrize("value", [0.5, None])
def test_removed_min_score_argument_is_refused(value):
    """Swallowed by **options, it would leave the operator with no score limit."""
    with pytest.raises(AltchaConfigurationError, match="max_score"):
        make_verifier(min_score=value)


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


def test_bound_field_without_fields_hash_rejected():
    """A client that skips classification (no fields sent to Sentinel) gets no pass."""
    payload = factories.make_sentinel_payload(SECRET)
    result = make_verifier(verify_fields=True).verify(payload, form_data={"message": "spam"})
    assert result.code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_bound_field_outside_signed_fields_rejected():
    payload = factories.make_sentinel_payload(
        SECRET, fields=["other"], field_values={"other": "x"}
    )
    result = make_verifier(verify_fields=True).verify(
        payload, form_data={"message": "spam", "other": "x"}
    )
    assert result.code == ErrorCode.FIELDS_HASH_MISMATCH.value


@pytest.mark.parametrize("empty", ["", None])
def test_empty_bound_field_need_not_be_signed(empty):
    """The widget never sends empty fields for classification."""
    v = make_verifier(verify_fields=True)
    assert v.verify(factories.make_sentinel_payload(SECRET), form_data={"message": empty}).verified
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}
    )
    result = v.verify(payload, form_data={"email": "a@b.com", "message": empty})
    assert result.verified


def test_unbound_form_ignores_missing_fields_hash():
    assert (
        make_verifier(verify_fields=True).verify(factories.make_sentinel_payload(SECRET)).verified
    )


def test_verify_fields_off_skips_binding():
    payload = factories.make_sentinel_payload(SECRET)
    result = make_verifier(verify_fields=False).verify(payload, form_data={"message": "spam"})
    assert result.verified


@pytest.mark.parametrize("name", ["123", "true", "1.5", "0"])
def test_single_field_name_that_looks_like_a_value(name):
    """Sentinel signs `fields=123`; parsing it as a number must not crash or lose it."""
    payload = factories.make_sentinel_payload(SECRET, fields=[name], field_values={name: "hi"})
    v = make_verifier(verify_fields=True)
    assert v.verify(payload, form_data={name: "hi"}).verified
    assert v.verify(payload, form_data={name: "spam"}).code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_remote_mode_binds_fields_from_the_signed_payload():
    """The response's verificationData is re-typed by Sentinel (fields=123 -> 123);
    the submitted, Sentinel-verified string is used instead."""
    payload = factories.make_sentinel_payload(SECRET, fields=["123"], field_values={"123": "hi"})
    response = {
        "verified": True,
        "verificationData": {"fields": 123, "fieldsHash": "x", "expire": 9_999_999_999},
    }
    v = make_verifier(mode="remote", verify_fields=True, http_post=_fake_post(response))
    assert v.verify(payload, form_data={"123": "hi"}).verified
    assert (
        v.verify(payload, form_data={"123": "spam"}).code == ErrorCode.FIELDS_HASH_MISMATCH.value
    )


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


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b"<html>gateway</html>"),
        (200, b"[1]"),
        (200, b'"ok"'),
        (200, b"\xff\xfe"),
        (400, b"[1]"),
        (200, b'{"verified": true, "verificationData": [1]}'),
        (200, b'{"verified": true, "verificationData": 5}'),
    ],
)
def test_remote_malformed_response_is_backend_error(status, body):
    """A proxy page or broken Sentinel must not raise out of form validation."""
    v = make_verifier(mode="remote", http_post=lambda *a: (status, body))
    result = v.verify(factories.make_sentinel_payload(SECRET))
    assert not result.verified
    assert result.code == ErrorCode.BACKEND_ERROR.value


def test_remote_non_string_reason_is_reported():
    v = make_verifier(mode="remote", http_post=_fake_post({"error": 5}, status=400))
    result = v.verify(factories.make_sentinel_payload(SECRET))
    assert result.code == ErrorCode.BACKEND_ERROR.value
    assert result.error == "5"


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


# --- fieldsHash is always SHA-256 ------------------------------------------
@pytest.mark.parametrize("algorithm", ["SHA-1", "SHA-256", "SHA-384", "SHA-512"])
def test_fields_hash_is_sha256_whatever_the_signature_algorithm(algorithm):
    """Sentinel signs v1 payloads with the challenge's SHA-* but always hashes fields
    with SHA-256; the payload's algorithm must not select the fieldsHash digest."""
    payload = factories.make_sentinel_payload(
        SECRET, fields=["email"], field_values={"email": "a@b.com"}, algorithm=algorithm
    )
    v = make_verifier(verify_fields=True)
    assert v.verify(payload, form_data={"email": "a@b.com"}).verified
    tampered = v.verify(payload, form_data={"email": "evil@x.com"})
    assert tampered.code == ErrorCode.FIELDS_HASH_MISMATCH.value


def test_hostile_payload_algorithm_is_rejected_not_raised():
    """The payload names its own digest; an unknown one is a bad signature, not a crash."""
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
    assert result.code == ErrorCode.INVALID_SIGNATURE.value
