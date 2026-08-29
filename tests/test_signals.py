from __future__ import annotations

import pytest
from django.test import override_settings

from altcha_django.results import ErrorCode
from altcha_django.signals import (
    altcha_replayed,
    altcha_verification_failed,
    altcha_verified,
)
from altcha_django.verifiers import run_verification
from altcha_django.verifiers.local import LocalVerifier
from tests import factories

pytestmark = pytest.mark.django_db


class Collector:
    def __init__(self):
        self.events = []

    def __call__(self, sender, **kwargs):
        self.events.append((sender, kwargs))


@pytest.fixture
def signals():
    ok, fail, replay = Collector(), Collector(), Collector()
    altcha_verified.connect(ok)
    altcha_verification_failed.connect(fail)
    altcha_replayed.connect(replay)
    yield ok, fail, replay
    altcha_verified.disconnect(ok)
    altcha_verification_failed.disconnect(fail)
    altcha_replayed.disconnect(replay)


def test_success_fires_verified(signals):
    ok, fail, replay = signals
    run_verification(factories.make_pow_payload())
    assert len(ok.events) == 1
    assert ok.events[0][0] is LocalVerifier
    assert ok.events[0][1]["result"].verified
    assert not fail.events


def test_failure_fires_failed_with_code(signals):
    ok, fail, replay = signals
    run_verification(factories.make_tampered_pow_payload())
    assert not ok.events
    assert fail.events[0][1]["code"] == ErrorCode.INVALID_SIGNATURE.value


def test_replay_fires_both_replayed_and_failed(signals):
    ok, fail, replay = signals
    payload = factories.make_pow_payload()
    run_verification(payload)
    run_verification(payload)
    assert len(replay.events) == 1
    assert replay.events[0][1]["replay_id"]
    assert any(e[1]["code"] == ErrorCode.REPLAYED.value for e in fail.events)


def test_empty_submission_fires_nothing(signals):
    ok, fail, replay = signals
    run_verification("")
    assert not ok.events and not fail.events and not replay.events


@override_settings(ALTCHA_COLLECT_STATS=True)
def test_cache_stats_recorder():
    from altcha_django.stats import recorder

    recorder.connect()
    try:
        run_verification(factories.make_pow_payload())
        run_verification(factories.make_tampered_pow_payload())
        snap = recorder.snapshot()
    finally:
        recorder.disconnect()
    assert snap.get("ok:total", 0) >= 1
    assert snap.get("fail:total", 0) >= 1
