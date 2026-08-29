from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.results import ErrorCode, PayloadType
from altcha_django.verifiers.base import BaseVerifier
from altcha_django.verifiers.null import NullVerifier

pytestmark = pytest.mark.django_db


class Dummy(BaseVerifier):
    name = "dummy"

    def verify(self, payload, *, request=None, form_data=None):
        from altcha_django.results import VerificationResult

        return VerificationResult.success(payload_type=PayloadType.TEST)


def test_base_get_challenge_not_implemented():
    with pytest.raises(NotImplementedError):
        BaseVerifier().get_challenge()


def test_base_default_check_is_empty():
    assert BaseVerifier().check() == []


def test_base_widget_challenge_ref_is_none():
    assert BaseVerifier().get_widget_challenge_ref() is None


def test_base_test_payload_helper():
    assert BaseVerifier().verify_test_payload("x").verified
    assert BaseVerifier().verify_test_payload("") is None


async def test_base_averify_delegates():
    result = await Dummy().averify("x")
    assert result.verified


async def test_base_aget_challenge_delegates():
    challenge = await NullVerifier().aget_challenge()
    assert set(challenge) == {"parameters", "signature"}


def test_null_verifier_accepts_nonempty():
    assert NullVerifier().verify("anything").verified


def test_null_verifier_requires_value():
    assert NullVerifier().verify("").code == ErrorCode.REQUIRED.value


@override_settings(ALTCHA_HMAC_SECRET=None)
def test_null_verifier_get_challenge_without_secret():
    challenge = NullVerifier().get_challenge()
    assert set(challenge) == {"parameters", "signature"}
