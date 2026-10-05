from __future__ import annotations

import time

import pytest
from django.test import override_settings

from altcha_django.replay import ReplayProtector
from altcha_django.results import ErrorCode
from altcha_django.verifiers import run_verification
from tests import factories

pytestmark = pytest.mark.django_db


def test_first_use_then_replay():
    rp = ReplayProtector()
    assert rp.register("id-1", expires_at=int(time.time()) + 100) is True
    assert rp.register("id-1", expires_at=int(time.time()) + 100) is False


def test_scope_isolation():
    rp = ReplayProtector()
    assert rp.register("shared-id", scope="local") is True
    assert rp.register("shared-id", scope="sentinel") is True


def test_ttl_from_expiry(settings):
    rp = ReplayProtector(clock_skew=0)
    # expires in 1 second -> key should be gone shortly after
    rp.register("short", expires_at=int(time.time()) + 1)
    assert rp.seen("short")
    time.sleep(1.2)
    assert not rp.seen("short")


def test_fallback_ttl_used_without_expiry():
    rp = ReplayProtector(fallback_ttl=42)
    assert rp._ttl(None) == 42


def test_pipeline_marks_replay():
    payload = factories.make_pow_payload()
    assert run_verification(payload).verified
    replayed = run_verification(payload)
    assert not replayed.verified
    assert replayed.code == ErrorCode.REPLAYED.value


@override_settings(ALTCHA_REPLAY_PROTECTION=False)
def test_pipeline_replay_disabled():
    payload = factories.make_pow_payload()
    assert run_verification(payload).verified
    assert run_verification(payload).verified  # reuse allowed


def _sentinel(**kw):
    from altcha_django.verifiers import SentinelVerifier

    kw.setdefault("challenge_url", "https://sentinel.example/v1/challenge?apiKey=key_1")
    kw.setdefault("api_secret", factories.DEFAULT_SECRET)
    kw.setdefault("verify_fields", False)
    return SentinelVerifier(**kw)


def test_signed_payload_without_id_fails_closed():
    """A verified payload with nothing to claim would be reusable indefinitely."""
    payload = factories.make_sentinel_payload(omit_id=True)
    result = run_verification(payload, verifier=_sentinel())
    assert not result.verified
    assert result.code == ErrorCode.MALFORMED.value


def _remote_ok(response_vd):
    import json

    response_vd = {"expire": int(time.time()) + 600, **response_vd}

    def post(url, data, headers, timeout):
        return 200, json.dumps({"verified": True, "verificationData": response_vd}).encode()

    return _sentinel(mode="remote", http_post=post)


def test_remote_submitted_payload_without_id_fails_closed():
    verifier = _remote_ok({"verified": True, "id": "from-response"})
    result = run_verification(factories.make_sentinel_payload(omit_id=True), verifier=verifier)
    assert not result.verified
    assert result.code == ErrorCode.MALFORMED.value


def test_remote_claims_the_submitted_signed_id():
    """The id comes from the payload Sentinel verified, not the (coerced) response."""
    verifier = _remote_ok({"verified": True, "id": 123})
    first = factories.make_sentinel_payload(verification_id="0123")
    second = factories.make_sentinel_payload(verification_id="123")
    assert run_verification(first, verifier=verifier).replay_id == "0123"
    assert run_verification(second, verifier=verifier).verified


@pytest.mark.parametrize(("first", "second"), [("0123", "123"), ("1.10", "1.1"), (" abc ", "abc")])
def test_distinct_signed_ids_are_distinct_claims(first, second):
    """parse_verification_data coerces these to the same value; the claims must not."""
    for vid in (first, second):
        result = run_verification(
            factories.make_sentinel_payload(verification_id=vid), verifier=_sentinel()
        )
        assert result.verified, result.code
        assert result.replay_id == vid


def test_signed_id_zero_is_a_valid_claim():
    payload = factories.make_sentinel_payload(verification_id="0")
    assert run_verification(payload, verifier=_sentinel()).verified
    assert run_verification(payload, verifier=_sentinel()).code == ErrorCode.REPLAYED.value


@override_settings(ALTCHA_REPLAY_FALLBACK_TTL=600)
def test_payload_without_expire_is_bounded_by_signed_time():
    """Accepting it after its replay entry lapsed would allow reuse."""
    old = factories.make_sentinel_payload(expire_in=None, age=601)
    assert run_verification(old, verifier=_sentinel()).code == ErrorCode.EXPIRED.value

    fresh = factories.make_sentinel_payload(expire_in=None, age=590)
    result = run_verification(fresh, verifier=_sentinel())
    assert result.verified
    # Replay entries live until expires_at (+ skew), i.e. the whole acceptance window.
    assert abs(result.expires_at - (int(time.time()) + 10)) <= 1


def test_signed_expire_takes_precedence_over_time():
    payload = factories.make_sentinel_payload(expire_in=60, age=10 * 86400)
    assert run_verification(payload, verifier=_sentinel()).verified


def test_payload_without_expire_or_time_is_refused():
    payload = factories.make_sentinel_payload(expire_in=None, age=None)
    assert run_verification(payload, verifier=_sentinel()).code == ErrorCode.MALFORMED.value


def test_custom_verifier_without_replay_id():
    from altcha_django.results import VerificationResult
    from altcha_django.verifiers import BaseVerifier

    class NoId(BaseVerifier):
        def verify(self, payload, *, request=None, form_data=None):
            return VerificationResult.success()

    assert run_verification("p", verifier=NoId()).code == ErrorCode.MALFORMED.value
    # Without replay protection there is no claim to make, so nothing to fail.
    assert run_verification("p", verifier=NoId(), replay=False).verified


@override_settings(ALTCHA_VERIFIER="null")
def test_null_verifier_is_exempt():
    assert run_verification("anything").verified
    assert run_verification("anything").verified


@override_settings(ALTCHA_CACHE_ALIAS="shared")
def test_uses_configured_cache_alias():
    from django.core.cache import caches

    rp = ReplayProtector()
    rp.register("x", expires_at=int(time.time()) + 100)
    assert caches["shared"].get(rp._key("x", "")) == 1
    assert caches["default"].get(rp._key("x", "")) is None
