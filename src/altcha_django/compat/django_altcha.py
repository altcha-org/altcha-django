"""Drop-in shim for a staged migration from ``django-altcha``.

``from altcha_django.compat.django_altcha import AltchaField`` accepts the old
keyword names and maps them onto the new API. Emits ``DeprecationWarning``.
Prefer the real :mod:`altcha_django` API for new code.
"""

from __future__ import annotations

import json
import warnings
from typing import Any

from ..forms import AltchaField as _AltchaField
from ..forms import AltchaMixin, AltchaModelFormMixin
from ..widgets import AltchaWidget as _AltchaWidget

__all__ = ["AltchaField", "AltchaWidget", "AltchaMixin", "AltchaModelFormMixin"]

# old kwarg -> ("rename", new_kwarg) | ("config", configuration_key) | ("drop", reason)
_MAP: dict[str, tuple[str, str]] = {
    "challengeurl": ("rename", "challenge_url"),
    "challengejson": ("rename", "challenge"),
    "floating": ("rename", "floating"),
    "auto": ("rename", "auto"),
    "debug": ("config", "debug"),
    "test": ("rename", "widget_test"),
    "mockerror": ("config", "mockError"),
    "hidefooter": ("config", "hideFooter"),
    "hidelogo": ("config", "hideLogo"),
    "workers": ("rename", "workers"),
    "language": ("rename", "language"),
    "delay": ("config", "minDuration"),
    "expire": ("drop", "challenge expiry now comes from ALTCHA_CHALLENGE['expires_seconds']"),
    "maxnumber": ("drop", "proof-of-work v2 has no maxnumber"),
    "strings": ("drop", "use the widget's global $altcha.i18n registry"),
    "refetchonexpire": ("drop", "the v3 widget always refetches on expiry"),
}


def _translate(kwargs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    config: dict[str, Any] = dict(kwargs.pop("configuration", {}) or {})
    for key, value in list(kwargs.items()):
        rule = _MAP.get(key)
        if rule is None:
            out[key] = value
            continue
        warnings.warn(
            f"altcha-django: '{key}' is a django-altcha name; use the altcha_django API instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        action, target = rule
        if action == "rename":
            out[target] = (
                json.dumps(value)
                if key == "challengejson" and not isinstance(value, (str, dict))
                else value
            )
        elif action == "config":
            config[target] = value
        elif action == "drop":
            warnings.warn(
                f"altcha-django: ignoring '{key}' — {target}", DeprecationWarning, stacklevel=3
            )
    if config:
        out["configuration"] = config
    return out


class AltchaField(_AltchaField):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **_translate(kwargs))


class AltchaWidget(_AltchaWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **_translate(kwargs))
