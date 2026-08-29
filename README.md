# altcha-django

Django integration for [ALTCHA](https://altcha.org) — built around **Widget v3**,
**Proof-of-Work v2**, and **ALTCHA Sentinel**.

- A real Django form field (`Form`, `ModelForm`, formsets, `Widget.Media`, translated errors).
- Pluggable verification backend: **local** proof-of-work or **Sentinel** (local
  server-signature verification or the remote API).
- Atomic replay protection via Django's cache framework.
- Signals for every verification outcome; optional built-in stats.
- Test mode and `django check` system checks.
- Optional Django REST Framework field.

> Requires Python 3.10+ and Django 4.2+.

## Install

```console
pip install altcha-django
# extras: [sentinel] (httpx), [argon2] (argon2-cffi), [drf] (djangorestframework)
```

## Quick start — local verification

```python
# settings.py
INSTALLED_APPS = [..., "altcha_django"]
ALTCHA_HMAC_SECRET = "a-long-random-string"   # keep secret

# urls.py
urlpatterns = [..., path("altcha/", include("altcha_django.urls"))]

# forms.py
from django import forms
from altcha_django import AltchaField, AltchaMixin

class ContactForm(AltchaMixin, forms.Form):
    email = forms.EmailField()
    captcha = AltchaField()
```

```python
# views.py
form = ContactForm(request.POST or None, request=request)
```

```django
{{ form.media }}
<form method="post">{% csrf_token %}{{ form.as_p }}<button>Send</button></form>
```

## Quick start — Sentinel

```python
ALTCHA_VERIFIER = "sentinel"
# Full challenge URL of your self-hosted Sentinel, API key in the query string:
ALTCHA_SENTINEL_CHALLENGE_URL = "https://sentinel.example.com/v1/challenge?apiKey=key_..."
ALTCHA_SENTINEL_API_SECRET = "sec_..."   # private — never leaves the server
```

Nothing else changes: the widget fetches its challenge from your Sentinel and the
field verifies the signed result locally. Read `score` / `classification` with
`AltchaField(return_result=True)`.

See [`docs/`](docs/) for the full settings reference, signals, system checks,
Sentinel guide, testing notes, and migration from `django-altcha`.

## License

MIT
