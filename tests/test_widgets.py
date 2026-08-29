from __future__ import annotations

import pytest
from django.test import override_settings
from django.utils import translation

from altcha_django.widgets import AltchaWidget, widget_i18n_js_url, widget_js_url

pytestmark = pytest.mark.django_db


def render(**kw):
    return AltchaWidget(**kw).render("altcha", None)


def test_default_uses_challenge_endpoint():
    html = render()
    assert 'challenge="/altcha/challenge/"' in html
    assert "<altcha-widget" in html


def test_inline_challenge_mode(settings):
    html = AltchaWidget(challenge_mode="inline").render("altcha", None)
    assert "challenge='" in html
    assert "parameters" in html


def test_explicit_challenge_url():
    html = render(challenge_url="https://example.com/c")
    assert 'challenge="https://example.com/c"' in html


def test_explicit_inline_dict_challenge():
    html = render(challenge={"parameters": {"x": 1}, "signature": "s"})
    assert "challenge='" in html


def test_language_follows_active_language():
    with translation.override("fr"):
        assert 'language="fr"' in render()


def test_language_override():
    assert 'language="de"' in render(language="de")


def test_configuration_json_is_escaped():
    html = render(configuration={"validationMessage": "</script><b>x"})
    assert "</script>" not in html
    assert "&lt;/script&gt;" in html or "\\u003c" in html


def test_floating_sugar():
    assert 'display="floating"' in render(floating=True)


@override_settings(ALTCHA_TEST_MODE=True)
def test_test_mode_goes_into_configuration_json():
    # The v3 element has no bare `test` attribute; test mode must travel in the
    # `configuration` JSON (rendered HTML-escaped inside the attribute).
    html = render()
    assert " test>" not in html and " test " not in html
    assert "&quot;test&quot;: true" in html


@override_settings(ALTCHA_TEST_MODE=True)
def test_test_mode_does_not_override_explicit_configuration():
    html = render(configuration={"test": False})
    assert "&quot;test&quot;: false" in html


def test_media_is_module_script():
    assert 'type="module"' in str(AltchaWidget().media)
    assert "altcha.min.js" in str(AltchaWidget().media)


@override_settings(ALTCHA_WIDGET_JS_SOURCE="cdn")
def test_media_cdn_source():
    assert widget_js_url().startswith("https://cdn.jsdelivr.net")


@override_settings(ALTCHA_WIDGET_JS_SOURCE="custom", ALTCHA_WIDGET_JS_URL="/assets/altcha.js")
def test_media_custom_source():
    assert widget_js_url() == "/assets/altcha.js"


@override_settings(ALTCHA_WIDGET_I18N=True)
def test_i18n_pack_appended():
    assert widget_i18n_js_url() is not None
    assert "i18n" in str(AltchaWidget().media)


def test_value_from_datadict():
    w = AltchaWidget()
    assert w.value_from_datadict({"altcha": "abc"}, {}, "altcha") == "abc"
    assert w.value_omitted_from_data({}, {}, "altcha") is True
    assert w.use_required_attribute(None) is False
    assert w.id_for_label("id_altcha") == ""


@override_settings(ALTCHA_WIDGET_CHALLENGE_MODE="endpoint")
def test_endpoint_mode_without_url_raises(settings):
    from django.urls import set_urlconf

    set_urlconf("tests.urls_empty")
    try:
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            AltchaWidget().render("altcha", None)
    finally:
        set_urlconf(None)


@override_settings(ALTCHA_WIDGET_CHALLENGE_MODE="auto")
def test_auto_mode_falls_back_to_inline_without_url():
    from django.urls import set_urlconf

    set_urlconf("tests.urls_empty")
    try:
        html = AltchaWidget().render("altcha", None)
        assert "challenge='" in html and "parameters" in html
    finally:
        set_urlconf(None)


_SENTINEL_URL = "https://sentinel.example.com/v1/challenge?apiKey=key_abc"


def test_sentinel_verifier_points_challenge_at_configured_url(settings):
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = _SENTINEL_URL
    settings.ALTCHA_SENTINEL_API_SECRET = "sec"
    html = AltchaWidget().render("altcha", None)
    assert f'challenge="{_SENTINEL_URL}"' in html


def test_sentinel_spamfilter_sets_verify_url(settings):
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = _SENTINEL_URL
    settings.ALTCHA_SENTINEL_API_SECRET = "sec"
    settings.ALTCHA_SENTINEL_SPAMFILTER = True
    html = AltchaWidget().render("altcha", None)
    assert "verifyUrl" in html
    assert "https://sentinel.example.com/v1/verify" in html


@override_settings(ALTCHA_WIDGET_DEFAULTS={"type": "switch", "hideLogo": True})
def test_unknown_widget_defaults_are_not_rendered():
    html = render()
    assert 'type="switch"' in html  # real attribute still applied
    assert "hideLogo" not in html  # inert key dropped (checks.W014 reports it)


@override_settings(ALTCHA_WIDGET_DEFAULTS={"name": "oops"})
def test_widget_defaults_cannot_duplicate_the_name_attribute():
    html = render()
    assert html.count("name=") == 1
    assert 'name="altcha"' in html


# --- standard Django `attrs` -------------------------------------------
def test_attrs_are_rendered_on_the_element():
    html = render(attrs={"class": "my-widget", "data-x": "1"})
    assert 'class="my-widget"' in html
    assert 'data-x="1"' in html


def test_attrs_follow_html_boolean_conventions():
    html = render(attrs={"disabled": True, "hidden": False})
    assert " disabled>" in html or " disabled " in html  # bare, not disabled="True"
    assert "hidden" not in html  # False is omitted entirely


def test_attrs_cannot_override_widget_managed_attributes():
    html = render(attrs={"name": "evil", "challenge": "https://evil.example.com"})
    assert html.count("name=") == 1
    assert 'name="altcha"' in html
    assert "evil.example.com" not in html
    assert 'challenge="/altcha/challenge/"' in html


def test_explicit_kwarg_beats_the_same_key_in_attrs():
    assert 'theme="light"' in render(theme="light", attrs={"theme": "dark"})


def test_element_attribute_may_come_from_attrs_alone():
    assert 'theme="dark"' in render(attrs={"theme": "dark"})


def test_language_from_attrs_survives_the_active_language_default():
    with translation.override("en"):
        assert 'language="fr"' in render(attrs={"language": "fr"})


def test_attrs_values_are_escaped():
    html = render(attrs={"class": '"><script>alert(1)</script>'})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_form_rendering_passes_djangos_auto_id_through():
    from django import forms

    from altcha_django import AltchaField

    class F(forms.Form):
        captcha = AltchaField(widget=AltchaWidget(attrs={"class": "c"}))

    html = str(F()["captcha"])
    assert 'id="id_captcha"' in html
    assert 'class="c"' in html
