from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_app_is_installed():
    from django.apps import apps

    config = apps.get_app_config("altcha_django")
    assert config.verbose_name == "ALTCHA"


def test_checks_are_registered():
    from django.core.checks.registry import registry

    names = {
        c.__name__
        for c in registry.get_checks(include_deployment_checks=True)
        if getattr(c, "__module__", "").endswith("altcha_django.checks")
    }
    assert {"check_config", "check_deploy"} <= names


def test_ready_connects_stats_when_enabled(settings):
    from altcha_django.apps import AltchaDjangoConfig
    from altcha_django.signals import altcha_verified
    from altcha_django.stats import recorder

    settings.ALTCHA_COLLECT_STATS = True
    recorder.disconnect()
    before = len(altcha_verified.receivers)
    try:
        AltchaDjangoConfig("altcha_django", __import__("altcha_django")).ready()
        assert len(altcha_verified.receivers) == before + 1
    finally:
        recorder.disconnect()
