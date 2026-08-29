from __future__ import annotations

import pytest
from django import forms
from django.utils import translation

from altcha_django import AltchaField, AltchaMixin
from altcha_django.widgets import AltchaWidget

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("lang", ["en", "de", "fr"])
def test_widget_language_tracks_active_language(lang):
    with translation.override(lang):
        assert f'language="{lang}"' in AltchaWidget().render("altcha", None)


def test_explicit_language_beats_active():
    with translation.override("en"):
        assert 'language="fr"' in AltchaWidget(language="fr").render("altcha", None)


def test_error_messages_are_lazy_and_resolvable():
    class F(AltchaMixin, forms.Form):
        captcha = AltchaField()

    for lang in ("en", "de", "fr"):
        with translation.override(lang):
            form = F({"captcha": "garbage!!"})
            form.is_valid()
            assert str(form.errors["captcha"][0])
