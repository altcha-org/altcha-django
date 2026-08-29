from __future__ import annotations

from django import forms

from altcha_django import AltchaField, AltchaMixin


class ContactForm(AltchaMixin, forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea)
    # bind_form_fields is only used by the Sentinel backend (fieldsHash); it is
    # harmless for local verification.
    captcha = AltchaField(bind_form_fields=["email"], return_result=True)
