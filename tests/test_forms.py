from __future__ import annotations

import pytest
from django import forms
from django.forms import formset_factory
from django.test import override_settings
from django.utils import translation

from altcha_django import AltchaField, AltchaMixin
from altcha_django.results import ErrorCode, VerificationResult
from tests import factories

pytestmark = pytest.mark.django_db


class SimpleForm(AltchaMixin, forms.Form):
    name = forms.CharField(required=False)
    captcha = AltchaField()


def test_valid_submission():
    form = SimpleForm({"captcha": factories.make_pow_payload()})
    assert form.is_valid(), form.errors


def test_missing_is_required_error():
    form = SimpleForm({"captcha": ""})
    assert not form.is_valid()
    assert form.errors["captcha"].as_data()[0].code == ErrorCode.REQUIRED.value


def test_invalid_payload_error_code():
    form = SimpleForm({"captcha": factories.make_tampered_pow_payload()})
    assert not form.is_valid()
    assert form.errors["captcha"].as_data()[0].code == ErrorCode.INVALID_SIGNATURE.value


def test_replay_across_two_submissions():
    payload = factories.make_pow_payload()
    assert SimpleForm({"captcha": payload}).is_valid()
    form = SimpleForm({"captcha": payload})
    assert not form.is_valid()
    assert form.errors["captcha"].as_data()[0].code == ErrorCode.REPLAYED.value


def test_return_result_option():
    class F(AltchaMixin, forms.Form):
        captcha = AltchaField(return_result=True)

    form = F({"captcha": factories.make_pow_payload()})
    assert form.is_valid(), form.errors
    assert isinstance(form.cleaned_data["captcha"], VerificationResult)


def test_translated_error_message():
    with translation.override("de"):
        form = SimpleForm({"captcha": ""})
        form.is_valid()
        msg = str(form.errors["captcha"][0])
    # 'de' catalog is empty in tests -> falls back to the English source string,
    # but the lazy proxy must resolve without error and be non-empty.
    assert msg


def test_widget_options_passthrough_without_subclassing():
    field = AltchaField(
        display="bar", type="switch", auto="onsubmit", configuration={"debug": True}
    )
    html = field.widget.render("captcha", None)
    assert 'display="bar"' in html
    assert 'type="switch"' in html
    assert 'auto="onsubmit"' in html
    assert "debug" in html


def test_formset_independent_validation():
    FS = formset_factory(SimpleForm, extra=2)
    payload = factories.make_pow_payload()
    data = {
        "form-TOTAL_FORMS": "2",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-captcha": payload,
        "form-1-captcha": payload,  # same payload -> second form replay-fails
    }
    formset = FS(data)
    assert not formset.is_valid()
    assert formset.forms[0].is_valid()
    assert not formset.forms[1].is_valid()


def test_formset_empty_extra_forms_are_optional():
    FS = formset_factory(SimpleForm, extra=1)
    data = {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    formset = FS(data)
    assert formset.is_valid(), formset.errors


@override_settings(ALTCHA_VERIFIER="null")
def test_null_verifier_accepts_any_nonempty_payload():
    form = SimpleForm({"captcha": "anything"})
    assert form.is_valid(), form.errors


def test_bind_form_fields_feeds_sentinel(settings):
    settings.ALTCHA_VERIFIER = "sentinel"
    settings.ALTCHA_SENTINEL_CHALLENGE_URL = "https://s.example.com/v1/challenge?apiKey=k"
    settings.ALTCHA_SENTINEL_API_SECRET = "secret"

    class F(AltchaMixin, forms.Form):
        email = forms.EmailField()
        captcha = AltchaField(bind_form_fields=["email"])

    payload = factories.make_sentinel_payload(
        "secret", fields=["email"], field_values={"email": "a@b.com"}
    )
    form = F({"email": "a@b.com", "captcha": payload})
    assert form.is_valid(), form.errors

    bad = F(
        {
            "email": "a@b.com",
            "captcha": factories.make_sentinel_payload(
                "secret", fields=["email"], field_values={"email": "other@x.com"}
            ),
        }
    )
    assert not bad.is_valid()
    assert bad.errors["captcha"].as_data()[0].code == ErrorCode.FIELDS_HASH_MISMATCH.value
