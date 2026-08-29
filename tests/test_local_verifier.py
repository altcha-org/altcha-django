from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.results import ErrorCode, PayloadType
from altcha_django.verifiers import get_verifier
from altcha_django.verifiers.local import LocalVerifier
from tests import factories

pytestmark = pytest.mark.django_db

SECRET = "test-hmac-secret"


def verify(payload, **kw):
    return LocalVerifier(hmac_secret=SECRET).verify(payload, **kw)


def test_valid_payload():
    result = verify(factories.make_pow_payload(SECRET))
    assert result.verified
    assert result.payload_type == PayloadType.POW_V2
    assert result.replay_id
    assert result.expires_at


def test_valid_probabilistic_payload():
    result = verify(factories.make_probabilistic_pow_payload(SECRET))
    assert result.verified
    assert result.payload_type == PayloadType.POW_V2


def test_empty_payload_is_required():
    assert verify("").code == ErrorCode.REQUIRED.value


def test_garbage_payload_is_malformed():
    assert verify(factories.make_garbage_payload()).code == ErrorCode.MALFORMED.value


def test_v1_shaped_payload_rejected():
    result = verify(factories.make_v1_shaped_payload())
    assert not result.verified
    assert result.code == ErrorCode.MALFORMED.value


def test_server_signature_payload_rejected_by_local():
    result = verify(factories.make_sentinel_payload(SECRET))
    assert result.code == ErrorCode.MALFORMED.value


def test_tampered_signature():
    result = verify(factories.make_tampered_pow_payload(SECRET))
    assert result.code == ErrorCode.INVALID_SIGNATURE.value


def test_wrong_solution():
    result = verify(factories.make_wrong_solution_payload(SECRET))
    assert result.code == ErrorCode.INVALID_SOLUTION.value


def test_expired_challenge():
    result = verify(factories.make_expired_pow_payload(SECRET))
    assert result.code == ErrorCode.EXPIRED.value


def test_unsigned_challenge_rejected():
    result = verify(factories.make_unsigned_pow_payload())
    assert result.code == ErrorCode.INVALID_SIGNATURE.value


def test_wrong_secret_fails():
    result = LocalVerifier(hmac_secret="other").verify(factories.make_pow_payload(SECRET))
    assert result.code == ErrorCode.INVALID_SIGNATURE.value


@override_settings(ALTCHA_HMAC_SECRET=None)
def test_missing_secret_is_misconfigured():
    result = LocalVerifier().verify(factories.make_pow_payload(SECRET))
    assert result.code == ErrorCode.MISCONFIGURED.value


def test_replay_id_prefers_challenge_id_from_data():
    payload = factories.make_pow_payload(SECRET, data={"id": "fixed-id"})
    assert verify(payload).replay_id == "fixed-id"


@override_settings(ALTCHA_VERIFIER="local")
def test_get_verifier_returns_local():
    assert isinstance(get_verifier(), LocalVerifier)


def test_get_challenge_roundtrips():
    challenge = LocalVerifier(hmac_secret=SECRET).get_challenge()
    assert set(challenge) == {"parameters", "signature"}


def test_get_challenge_with_session_binding_embeds_token():
    challenge = LocalVerifier(hmac_secret=SECRET, bind_session=True).get_challenge()
    assert "id" in challenge["parameters"]["data"]


class _FakeSession(dict):
    pass


class _FakeRequest:
    def __init__(self, tokens):
        self.session = _FakeSession(altcha_challenges=list(tokens))


def test_session_binding_accepts_known_token():
    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    payload = factories.make_pow_payload(SECRET, data={"id": "tok-1"})
    req = _FakeRequest(["tok-1"])
    result = v.verify(payload, request=req)
    assert result.verified
    assert "tok-1" not in req.session["altcha_challenges"]  # consumed


def test_session_binding_rejects_unknown_token():
    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    payload = factories.make_pow_payload(SECRET, data={"id": "tok-x"})
    result = v.verify(payload, request=_FakeRequest([]))
    assert not result.verified
    assert result.code == ErrorCode.INVALID_SOLUTION.value


def test_session_binding_without_request_fails_closed():
    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    payload = factories.make_pow_payload(SECRET, data={"id": "tok-y"})
    result = v.verify(payload)
    assert not result.verified
    # a missing request is the developer's problem, not a bad solution
    assert result.code == ErrorCode.MISCONFIGURED.value
    assert "AltchaMixin" in result.error


def test_session_binding_without_session_middleware_is_misconfigured():
    class _NoSession:
        pass

    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    payload = factories.make_pow_payload(SECRET, data={"id": "tok-z"})
    result = v.verify(payload, request=_NoSession())
    assert not result.verified
    assert result.code == ErrorCode.MISCONFIGURED.value
    assert "SessionMiddleware" in result.error


def test_session_binding_rejects_challenge_never_registered():
    """An inline-minted challenge is never stored in the session, so it can't be redeemed.

    At runtime that is indistinguishable from a token minted for another session
    (both are just "absent"), which is why ``checks.E006`` rejects the inline +
    bind_session combination at startup instead.
    """
    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    payload = factories.make_pow_payload(SECRET)  # falls back to the challenge nonce
    result = v.verify(payload, request=_FakeRequest([]))
    assert not result.verified
    assert result.code == ErrorCode.INVALID_SOLUTION.value


def test_check_session_binding_predicate_still_works():
    v = LocalVerifier(hmac_secret=SECRET, bind_session=True)
    assert v.check_session_binding(_FakeRequest(["tok-a"]), "tok-a") is True
    assert v.check_session_binding(_FakeRequest([]), "tok-a") is False
    assert v.check_session_binding(None, "tok-a") is False
    # disabled -> always allowed
    assert LocalVerifier(hmac_secret=SECRET).check_session_binding(None, None) is True
