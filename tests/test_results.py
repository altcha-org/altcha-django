from __future__ import annotations

from altcha_django.results import (
    Classification,
    ErrorCode,
    PayloadType,
    VerificationResult,
)


def test_enum_str():
    assert str(PayloadType.POW_V2) == "pow_v2"
    assert str(Classification.BAD) == "BAD"
    assert str(ErrorCode.EXPIRED) == "expired"
    assert f"{PayloadType.TEST}" == "test"


def test_success_and_failure_constructors():
    ok = VerificationResult.success(score=0.5)
    assert ok.verified and ok.ok and ok.code is None and ok.score == 0.5

    fail = VerificationResult.failure(ErrorCode.EXPIRED, error="nope")
    assert not fail.verified
    assert fail.code == "expired"
    assert fail.error == "nope"


def test_result_is_frozen():
    import dataclasses

    r = VerificationResult.success()
    try:
        r.verified = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("VerificationResult should be immutable")
