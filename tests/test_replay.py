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


@override_settings(ALTCHA_CACHE_ALIAS="shared")
def test_uses_configured_cache_alias():
    from django.core.cache import caches

    rp = ReplayProtector()
    rp.register("x", expires_at=int(time.time()) + 100)
    assert caches["shared"].get(rp._key("x", "")) == 1
    assert caches["default"].get(rp._key("x", "")) is None
