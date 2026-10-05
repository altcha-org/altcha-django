# ALTCHA Sentinel

[Sentinel](https://altcha.org/docs/sentinel/) is ALTCHA's **self-hosted**
security layer: it issues challenges, verifies solutions, and classifies each
request (`GOOD` / `NEUTRAL` / `BAD`, plus a numeric `score`).

## Configure

Two values — the full challenge URL of *your* Sentinel instance (with the API key
already in the query string), and the API key's secret:

```python
ALTCHA_VERIFIER = "sentinel"
ALTCHA_SENTINEL_CHALLENGE_URL = "https://sentinel.example.com/v1/challenge?apiKey=key_..."
ALTCHA_SENTINEL_API_SECRET = "sec_..."   # private — the HMAC secret for local verification
```

The challenge URL is handed straight to the browser widget; `AltchaField`
verifies the **signed result** locally with `ALTCHA_SENTINEL_API_SECRET` — no
extra network call from your server.

## Verification modes

| `ALTCHA_SENTINEL_MODE` | What happens |
|---|---|
| `"local"` (default) | `altcha.verify_server_signature()` with `ALTCHA_SENTINEL_API_SECRET`. No network. |
| `"remote"` | POSTs to Sentinel's `/v1/verify/signature` (derived from the challenge URL, or set `ALTCHA_SENTINEL_VERIFY_URL`). Sentinel enforces single-use. |

## Policy

```python
ALTCHA_SENTINEL_REJECT_CLASSIFICATIONS = ["BAD"]   # default
ALTCHA_SENTINEL_MIN_SCORE = None                    # e.g. 0.5 to also reject low scores
```

Rejections surface as `code="classification_rejected"` / `code="score_rejected"`.

Read the verdict in your view:

```python
captcha = AltchaField(return_result=True)
...
result = form.cleaned_data["captcha"]
result.classification, result.score, result.verification_data
```

## Field binding (`fieldsHash`)

Off by default, since Sentinel's default setup classifies no fields. With the
spam filter enabled, the widget sends the form's text fields to Sentinel for
classification, and Sentinel signs their names (`fields`) and a hash of their
values (`fieldsHash`). Binding those fields makes sure the submitted values are
the ones that were classified:

```python
ALTCHA_SENTINEL_SPAMFILTER = True      # widget sends fields to Sentinel /v1/verify
ALTCHA_SENTINEL_VERIFY_FIELDS = True   # enforce fieldsHash for bound fields

class ContactForm(AltchaMixin, forms.Form):
    message = forms.CharField(widget=forms.Textarea)
    captcha = AltchaField(bind_form_fields=["message"])
```

Every bound field submitted with a non-empty value must be covered by the signed
hash; otherwise the submission fails with `code="fields_hash_mismatch"`. That
covers a value changed after verification, and a payload obtained without sending
the field for classification at all (no `fieldsHash`, or the field missing from
`fields`). Empty bound fields are exempt, as the widget never sends them.

List fields by their form field name; with a form `prefix`, the prefixed HTML
name (`contact-message`) is matched against Sentinel's `fields` automatically.
Text inputs the widget hashed but that are not bound still count toward the hash,
so changing any of them after verification also fails.

The widget only collects `<input type="text">` and `<textarea>` elements with a
value and without `data-no-spamfilter`. Bind only fields rendered that way:
an `EmailField` renders `type="email"`, is never classified, and would fail every
non-empty submission. With `ALTCHA_SENTINEL_VERIFY_FIELDS = False` (the default),
`bind_form_fields` has no effect.

## Same-origin challenge proxy

```python
ALTCHA_SENTINEL_PROXY_CHALLENGE = True
# urls.py already includes altcha_django.urls -> /altcha/sentinel/challenge/
```

The proxy view fetches `ALTCHA_SENTINEL_CHALLENGE_URL` server-side and returns it
under your own origin — no cross-origin request from the browser, and a place to
add caching / rate-limiting. The challenge JSON is relayed unchanged, including
the `configuration` property Sentinel uses to configure the widget.

## httpx transport

By default Sentinel is reached with the stdlib `urllib`, which opens a fresh
connection per call. The package ships pooled `httpx` replacements:

```console
pip install 'altcha-django[sentinel]'
```

```python
ALTCHA_SENTINEL_HTTP_POST = "altcha_django.transports.httpx_post"  # remote-mode verification
ALTCHA_SENTINEL_HTTP_GET = "altcha_django.transports.httpx_get"    # challenge proxy fetches
```

Both share one lazily-created, thread-safe `httpx.Client` (rebuilt automatically
if the process forks). `altcha_django.transports.close_client()` closes it, e.g.
from a worker-shutdown hook.

To use another HTTP client, point the settings at your own callables instead —
`http_post(url, body, headers, timeout) -> (status, bytes)` and
`http_get(url, headers, timeout) -> (status, bytes)`. Either setting
accepts a dotted path or a callable.
