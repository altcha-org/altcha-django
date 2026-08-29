from __future__ import annotations

import pytest


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
