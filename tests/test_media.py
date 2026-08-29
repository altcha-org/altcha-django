from __future__ import annotations

import pytest
from django import forms
from django.forms import formset_factory
from django.test import override_settings

from altcha_django import AltchaField
from altcha_django.widgets import AltchaWidget, ModuleScript

pytestmark = pytest.mark.django_db


class F(forms.Form):
    a = AltchaField()


def test_module_script_html():
    tag = ModuleScript("/x/altcha.min.js").__html__()
    assert tag == '<script type="module" src="/x/altcha.min.js"></script>'


def test_module_script_equality_and_hash():
    assert ModuleScript("/a") == ModuleScript("/a")
    assert ModuleScript("/a") != ModuleScript("/b")
    assert len({ModuleScript("/a"), ModuleScript("/a")}) == 1


def test_media_renders_module_type():
    html = str(F().media)
    assert 'type="module"' in html
    assert "altcha.min.js" in html


def test_media_dedups_across_formset():
    FS = formset_factory(F, extra=3)
    html = str(FS().media)
    assert html.count("altcha.min.js") == 1


def test_media_survives_form_composition():
    class G(forms.Form):
        b = AltchaField()

    combined = str(F().media + G().media)
    assert combined.count("altcha.min.js") == 1
    assert 'type="module"' in combined


@override_settings(ALTCHA_WIDGET_I18N=True, ALTCHA_WIDGET_JS_SOURCE="cdn")
def test_i18n_pack_from_cdn_appended():
    html = str(AltchaWidget().media)
    assert html.count("<script") == 2
    assert "i18n" in html
