"""App configuration."""

from __future__ import annotations

from django.apps import AppConfig


class AltchaDjangoConfig(AppConfig):
    name = "altcha_django"
    verbose_name = "ALTCHA"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Register system checks.
        from . import checks  # noqa: F401

        # Opt-in stats receiver.
        from .conf import conf

        if conf.COLLECT_STATS:
            from .stats import recorder

            recorder.connect()
