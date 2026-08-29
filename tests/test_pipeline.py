from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.exceptions import AltchaConfigurationError
from altcha_django.results import ErrorCode, PayloadType, VerificationResult
from altcha_django.verifiers import (
    BaseVerifier,
    NullVerifier,
    get_verifier,
    register_verifier,
    resolve_verifier,
    run_averification,
    run_verification,
)
from altcha_django.verifiers.local import LocalVerifier
from tests import factories

pytestmark = pytest.mark.django_db


def test_empty_payload_short_circuits_without_signal():
    from altcha_django.signals import altcha_verification_failed

    seen = []

    def receiver(**kw):
        seen.append(kw)

    altcha_verification_failed.connect(receiver, weak=False)
    try:
        result = run_verification("")
    finally:
        altcha_verification_failed.disconnect(receiver)
    assert result.code == ErrorCode.REQUIRED.value
    assert seen == []


def test_resolve_verifier_variants():
    assert isinstance(resolve_verifier(None), LocalVerifier)
    assert isinstance(resolve_verifier("null"), NullVerifier)
    assert isinstance(resolve_verifier(NullVerifier), NullVerifier)
    inst = NullVerifier()
    assert resolve_verifier(inst) is inst
    with pytest.raises(TypeError):
        resolve_verifier(123)


def test_get_verifier_dotted_path():
    v = get_verifier("altcha_django.verifiers.local.LocalVerifier")
    assert isinstance(v, LocalVerifier)


def test_get_verifier_bad_alias():
    with pytest.raises(AltchaConfigurationError):
        get_verifier("nope.NotReal")


def test_get_verifier_non_verifier_dotted_path():
    with pytest.raises(AltchaConfigurationError):
        get_verifier("altcha_django.results.VerificationResult")


def test_register_verifier_roundtrip():
    class MyVerifier(BaseVerifier):
        name = "mine"

        def verify(self, payload, *, request=None, form_data=None):
            return VerificationResult.success(payload_type=PayloadType.TEST)

    register_verifier("mine", MyVerifier)
    try:
        assert run_verification("x", verifier="mine").verified
    finally:
        from altcha_django import verifiers

        verifiers._REGISTRY.pop("mine", None)
        verifiers._INSTANCES.pop("mine", None)

    with pytest.raises(TypeError):
        register_verifier("bad", dict)


@override_settings(ALTCHA_TEST_MODE=True)
def test_test_mode_bypass_with_signal():
    from altcha_django.signals import altcha_verified

    seen = []

    def receiver(**kw):
        seen.append(kw)

    altcha_verified.connect(receiver, weak=False)
    try:
        result = run_verification("literally-anything")
    finally:
        altcha_verified.disconnect(receiver)
    assert result.verified
    assert result.payload_type == PayloadType.TEST
    assert len(seen) == 1


async def test_run_averification_success():
    result = await run_averification(factories.make_pow_payload())
    assert result.verified


async def test_run_averification_replay():
    payload = factories.make_pow_payload()
    assert (await run_averification(payload)).verified
    replayed = await run_averification(payload)
    assert replayed.code == ErrorCode.REPLAYED.value


async def test_run_averification_empty():
    assert (await run_averification("")).code == ErrorCode.REQUIRED.value


@override_settings(ALTCHA_TEST_MODE=True)
async def test_run_averification_test_mode():
    assert (await run_averification("x")).verified
