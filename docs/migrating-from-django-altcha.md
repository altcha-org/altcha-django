# Migrating from `django-altcha`

`altcha-django` is a from-scratch library, not a fork. This guide covers moving
from `aboutcode-org/django-altcha`.

## What changes

| Area | `django-altcha` | `altcha-django` |
|---|---|---|
| Proof-of-work | v1 | **v2 only** (v1 payloads rejected) |
| Widget attributes | `challengeurl`, `challengejson`, `floating`, `expire`, `maxnumber` | `challenge`, `configuration`, `display`, `type` (Widget v3) |
| Assets | hand-written `<script>` tags in a template | `Widget.Media` → `<script type="module">` |
| Verification | PoW only | pluggable: `local` **or** `sentinel` |
| Replay check | `cache.get` then `cache.set` (racy) | atomic `cache.add`, on by default |
| Request access | none | `AltchaMixin` |
| Hooks | logging only | `altcha_verified` / `altcha_verification_failed` / `altcha_replayed` + stats |
| Config validation | none | `django check` (`altcha.E0xx` / `W0xx`) |

## Steps

1. **Swap the dependency and app label.**

   ```diff
   - INSTALLED_APPS = [..., "django_altcha"]
   + INSTALLED_APPS = [..., "altcha_django"]
   ```

2. **Settings.** The old names keep working for one release (with `altcha.W010`).
   Rename at your leisure:

   | old | new |
   |---|---|
   | `ALTCHA_HMAC_KEY` | `ALTCHA_HMAC_SECRET` |
   | `ALTCHA_CHALLENGE_EXPIRE` (ms) | `ALTCHA_CHALLENGE["expires_seconds"]` (s) |
   | `ALTCHA_JS_URL` | `ALTCHA_WIDGET_JS_URL` (+ `ALTCHA_WIDGET_JS_SOURCE = "custom"`) |
   | `ALTCHA_JS_TRANSLATIONS_URL` | `ALTCHA_WIDGET_I18N_JS_URL` |
   | `ALTCHA_INCLUDE_TRANSLATIONS` | `ALTCHA_WIDGET_I18N` |
   | `ALTCHA_VERIFICATION_ENABLED = False` | `ALTCHA_VERIFIER = "null"` |

3. **URLs.**

   ```diff
   - path("altcha/challenge/", AltchaChallengeView.as_view(), name="altcha_challenge"),
   + path("altcha/", include("altcha_django.urls")),   # name: altcha_django:challenge
   ```

4. **Forms.**

   ```diff
   - from django_altcha import AltchaField
   - captcha = AltchaField(challengeurl=reverse_lazy("altcha_challenge"), floating=True)
   + from altcha_django import AltchaField, AltchaMixin
   + captcha = AltchaField(display="floating")   # challenge URL resolved automatically
   ```

   Add `AltchaMixin` to the form class and pass `request=` from the view if you
   use Sentinel or want request context.

5. **Remove manual `<script>` includes** for `altcha.min.js` — `{{ form.media }}`
   handles it now.

6. **Run `python manage.py check`** and clear any `altcha.E*` errors.

## Staged migration shim

If you need to move gradually, `altcha_django.compat.django_altcha` re-exports
`AltchaField` / `AltchaWidget` accepting the old keyword names
(`challengeurl`, `challengejson`, `floating`) and mapping them across.
