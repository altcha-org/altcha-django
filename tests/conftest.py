from __future__ import annotations

import pytest


def pytest_report_header(config):
    """Show which backend holds replay claims, so a Redis CI run is visibly on Redis."""
    from django.conf import settings

    return f"altcha replay cache: {settings.CACHES['default']['BACKEND']}"


@pytest.fixture(autouse=True)
def _clear_caches():
    """Isolate replay/stats state between tests."""
    from django.core.cache import caches

    for alias in ("default", "shared", "dummy"):
        try:
            caches[alias].clear()
        except Exception:
            pass
    yield


@pytest.fixture(autouse=True)
def _reset_verifier_cache():
    from altcha_django import verifiers

    verifiers._INSTANCES.clear()
    yield
    verifiers._INSTANCES.clear()
