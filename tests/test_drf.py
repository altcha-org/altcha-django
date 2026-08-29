from __future__ import annotations

import pytest

rest_framework = pytest.importorskip("rest_framework")

from rest_framework import serializers  # noqa: E402

from altcha_django.contrib.rest_framework import AltchaField  # noqa: E402
from altcha_django.results import ErrorCode  # noqa: E402
from tests import factories  # noqa: E402

pytestmark = pytest.mark.django_db


class ContactSerializer(serializers.Serializer):
    email = serializers.EmailField()
    altcha = AltchaField(bind_fields=["email"])


def test_valid():
    s = ContactSerializer(data={"email": "a@b.com", "altcha": factories.make_pow_payload()})
    assert s.is_valid(), s.errors


def test_invalid_payload():
    s = ContactSerializer(
        data={"email": "a@b.com", "altcha": factories.make_tampered_pow_payload()}
    )
    assert not s.is_valid()
    assert s.errors["altcha"][0].code == ErrorCode.INVALID_SIGNATURE.value


def test_missing_payload():
    s = ContactSerializer(data={"email": "a@b.com"})
    assert not s.is_valid()
    assert "altcha" in s.errors


def test_replay():
    payload = factories.make_pow_payload()
    assert ContactSerializer(data={"email": "a@b.com", "altcha": payload}).is_valid()
    s = ContactSerializer(data={"email": "a@b.com", "altcha": payload})
    assert not s.is_valid()
    assert s.errors["altcha"][0].code == ErrorCode.REPLAYED.value


def test_sentinel_fields_hash(settings):
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = "https://s.example.com/v1/challenge?apiKey=k"
    settings.ALTCHA_SENTINEL_API_SECRET = "secret"

    payload = factories.make_sentinel_payload(
        "secret", fields=["email"], field_values={"email": "a@b.com"}
    )
    s = ContactSerializer(data={"email": "a@b.com", "altcha": payload})
    assert s.is_valid(), s.errors


def test_return_result_option():
    class S(serializers.Serializer):
        altcha = AltchaField(return_result=True)

    s = S(data={"altcha": factories.make_pow_payload()})
    assert s.is_valid(), s.errors
    from altcha_django.results import VerificationResult

    assert isinstance(s.validated_data["altcha"], VerificationResult)


def test_unknown_code_falls_back_to_unverified(settings, monkeypatch):
    from altcha_django.contrib import rest_framework as drf
    from altcha_django.results import VerificationResult

    monkeypatch.setattr(
        drf,
        "run_verification",
        lambda *a, **k: VerificationResult.failure("some_new_code"),
    )

    class S(serializers.Serializer):
        altcha = AltchaField()

    s = S(data={"altcha": "x"})
    assert not s.is_valid()
    assert s.errors["altcha"][0].code == ErrorCode.UNVERIFIED.value


async def test_async_to_internal_value():
    field = AltchaField()

    class S(serializers.Serializer):
        altcha = AltchaField()

    field.bind("altcha", S())
    result = await field.ato_internal_value(factories.make_pow_payload())
    assert result
