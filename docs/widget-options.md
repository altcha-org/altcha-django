# Widget options

Every option is a keyword argument to `AltchaField` (or `AltchaWidget`). No
subclassing.

## Plain element attributes

| kwarg | `<altcha-widget>` attribute | values |
|---|---|---|
| `auto` | `auto` | `off` `onfocus` `onload` `onsubmit` |
| `display` | `display` | `standard` `bar` `floating` `overlay` `invisible` |
| `floating=True` | `display="floating"` | shortcut |
| `type` | `type` | `native` `checkbox` `switch` |
| `language` | `language` | ISO code; **defaults to Django's active language** |
| `workers` | `workers` | int |
| `theme` | `theme` | `auto` `light` `dark` |

## Ordinary HTML attributes — `attrs`

`attrs` works as on any Django widget, for styling and hooks:

```python
AltchaField(widget=AltchaWidget(attrs={"class": "my-captcha", "data-testid": "altcha"}))
```

They render on `<altcha-widget>` alongside its own attributes, following Django's
conventions (`True` renders bare, `False`/`None` are omitted, values are escaped),
and Django's auto `id` is included. The widget's own options win over the same key
in `attrs`, and `name`, `challenge` and `configuration` are managed by the field —
they cannot be set or overridden this way.

## Everything else — `configuration`

Anything in the v3 [`Configuration`](https://github.com/altcha-org/altcha) object
goes in the `configuration` dict; it is emitted as the `configuration='{...}'`
JSON attribute.

```python
AltchaField(
    display="floating",
    configuration={"hideFooter": True, "minDuration": 1000, "debug": True},
)
```

Project-wide defaults:

```python
ALTCHA_WIDGET_DEFAULTS = {"type": "switch", "display": "standard"}
ALTCHA_WIDGET_CONFIGURATION = {"hideFooter": True}
```

The two are not interchangeable. `ALTCHA_WIDGET_DEFAULTS` may only contain the
plain element attributes from the table above — the element ignores anything else,
so those keys are dropped at render time and reported by `altcha.W014`. Every
other widget option belongs in `ALTCHA_WIDGET_CONFIGURATION`. `name`, `challenge`
and `configuration` are set by the field itself and cannot be defaulted here.

## Where the challenge comes from

Resolution order for the widget's `challenge` attribute:

1. `AltchaField(challenge=<dict|json str>)` — inline;
2. `AltchaField(challenge_url=<url>)` — explicit URL;
3. the verifier (Sentinel points it at its own challenge endpoint);
4. `ALTCHA_WIDGET_CHALLENGE_MODE`: `endpoint` (the bundled view), `inline`
   (mint per render), or `auto` (endpoint if wired, else inline).

## Serving the widget JS

| `ALTCHA_WIDGET_JS_SOURCE` | URL used |
|---|---|
| `"vendored"` (default) | `static("altcha_django/altcha.min.js")` — pinned bundle shipped in the package |
| `"cdn"` | `ALTCHA_WIDGET_JS_CDN` (jsDelivr `altcha@3`) |
| `"custom"` | `ALTCHA_WIDGET_JS_URL` |

`{{ form.media }}` renders it as `<script type="module">`. Update the vendored
copy with `python manage.py altcha_vendor_widget --altcha-version 3`.

## Internationalization

Two independent pieces:

1. **Which language the widget shows** — the `language` attribute. `AltchaField`
   sets it from Django's active language (`translation.get_language()`), so with
   `LocaleMiddleware` the widget follows the request locale automatically.
   Override per field with `AltchaField(language="fr")`.

2. **Which languages are *available*** — the ALTCHA v3 bundle ships **English
   only**. For `language="de"` (etc.) to render German text you must also load
   the translations bundle:

   ```python
   ALTCHA_WIDGET_I18N = True
   ```

   This appends a second `<script type="module">` to `{{ form.media }}`:

   | `ALTCHA_WIDGET_I18N_JS_URL` | `ALTCHA_WIDGET_JS_SOURCE` | URL used |
   |---|---|---|
   | set | — | your value (e.g. a single-locale file: `static("altcha_django/i18n/de.js")`) |
   | unset | `"cdn"` | `ALTCHA_WIDGET_I18N_JS_CDN` (jsDelivr `altcha@3/dist/i18n/all.js`) |
   | unset | otherwise | `static("altcha_django/i18n/all.js")` — vendored all-locales bundle (~67 KB) |

   The all-locales bundle self-registers every ALTCHA locale on load; point
   `ALTCHA_WIDGET_I18N_JS_URL` at a per-locale file if you only need one.
   `manage.py altcha_vendor_widget --i18n` refreshes the vendored copy.

   Leaving `ALTCHA_WIDGET_I18N = False` (the default) is correct for
   English-only sites — no extra request.
