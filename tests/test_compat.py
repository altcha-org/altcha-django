from __future__ import annotations

import pytest

from altcha_django.compat.django_altcha import AltchaField, AltchaWidget

pytestmark = pytest.mark.django_db


def test_challengeurl_is_mapped():
    with pytest.warns(DeprecationWarning):
        field = AltchaField(challengeurl="/c/")
    assert field.widget.challenge_url == "/c/"


def test_floating_and_hidefooter_mapped():
    with pytest.warns(DeprecationWarning):
        field = AltchaField(floating=True, hidefooter=True)
    html = field.widget.render("altcha", None)
    assert 'display="floating"' in html
    assert "hideFooter" in html


def test_v1_only_kwargs_are_dropped_with_warning():
    with pytest.warns(DeprecationWarning):
        field = AltchaField(maxnumber=100000, expire=120000)
    # no crash, no maxnumber/expire attributes leak onto the widget
    assert not hasattr(field.widget, "maxnumber")


def test_widget_shim():
    with pytest.warns(DeprecationWarning):
        w = AltchaWidget(challengeurl="/x/")
    assert w.challenge_url == "/x/"
