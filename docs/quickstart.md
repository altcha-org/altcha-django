# Quick start

## 1. Install & register

```console
pip install altcha-django
```

```python
# settings.py
INSTALLED_APPS = [..., "altcha_django"]
ALTCHA_HMAC_SECRET = "a long random string, kept secret"
```

## 2. Wire the challenge endpoint (recommended)

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    ...,
    path("altcha/", include("altcha_django.urls")),
]
```

Without this the widget falls back to minting a challenge inline on every render;
`altcha check` will point it out (`altcha.W009`).

## 3. Add the field

```python
from django import forms
from altcha_django import AltchaField, AltchaMixin

class ContactForm(AltchaMixin, forms.Form):
    email = forms.EmailField()
    captcha = AltchaField()
```

`AltchaMixin` passes the request into the field (needed for Sentinel `fieldsHash`
and IP checks). It is optional for plain local verification.

## 4. Render

```python
def contact(request):
    form = ContactForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        ...  # verified
```

```django
{{ form.media }}
<form method="post">{% csrf_token %}{{ form.as_p }}<button>Send</button></form>
```

That's it. The widget solves the proof-of-work in the browser and submits a
hidden `altcha` field; `AltchaField` verifies it, enforces single-use, and fires
signals.
