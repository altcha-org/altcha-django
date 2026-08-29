# altcha-django

Django integration for [ALTCHA](https://altcha.org), built around **Widget v3**,
**Proof-of-Work v2**, and **ALTCHA Sentinel**.

## Why this library

- A real Django form field — `Form`, `ModelForm`, formsets, `Widget.Media`,
  translated validation errors, every widget option as a keyword argument.
- The Django form integration is **separate** from the verification backend. Pick
  `local` proof-of-work or `sentinel`, per project or per field, without
  subclassing anything.
- Replay protection is built in and atomic (Django cache `add`), on by default.
- Signals for every verification outcome; opt-in cache-backed stats.
- `django check` system checks catch misconfiguration before deploy.
- Optional Django REST Framework field.

## Requirements

- Python 3.10+
- Django 4.2+
- The [`altcha`](https://pypi.org/project/altcha/) package (installed automatically)

## Install

```console
pip install altcha-django
```

Extras: `altcha-django[sentinel]` (pooled httpx transports for Sentinel — see
[Sentinel](sentinel.md#httpx-transport)), `altcha-django[argon2]`
(Argon2id challenges), `altcha-django[drf]` (REST Framework field).
