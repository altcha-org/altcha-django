# System checks

Run `python manage.py check` (add `--deploy` for `W004`). Tag: `altcha`.

## Errors

| id | condition |
|---|---|
| `altcha.E001` | `altcha` package missing or `< 2.1.0` |
| `altcha.E002` | `ALTCHA_VERIFIER` cannot be resolved |
| `altcha.E003` | local verifier, not test mode, `ALTCHA_HMAC_SECRET` unset |
| `altcha.E004` | Sentinel local mode without `ALTCHA_SENTINEL_API_SECRET` |
| `altcha.E005` | Sentinel without a valid absolute `ALTCHA_SENTINEL_CHALLENGE_URL` |
| `altcha.E006` | `CHALLENGE_BIND_SESSION` on, but challenges are minted inline (mode `inline`, or URLs not wired) |
| `altcha.E007` | `ALTCHA_CACHE_ALIAS` not in `CACHES` |
| `altcha.E008` | `WIDGET_JS_SOURCE="custom"` without `ALTCHA_WIDGET_JS_URL` |
| `altcha.E009` | unknown `ALTCHA_CHALLENGE["algorithm"]` |
| `altcha.E010` | `ALTCHA_CHALLENGE["key_prefix"]` is not hex (probabilistic mode) |
| `altcha.E011` | `CHALLENGE_BIND_SESSION` on without `django.contrib.sessions` + `SessionMiddleware` |
| `altcha.E012` | `ALTCHA_TRUSTED_PROXIES` has entries that are not valid IPs/CIDRs |

## Warnings

| id | condition |
|---|---|
| `altcha.W001` | replay on + `LocMemCache` (per-process) |
| `altcha.W002` | replay on + `DummyCache` (no-op) |
| `altcha.W003` | replay protection disabled |
| `altcha.W004` | test mode on with `DEBUG=False` (deploy check) |
| `altcha.W005` | `ARGON2ID` without `argon2-cffi` |
| `altcha.W006` | challenge `cost` outside 1000–500000 |
| `altcha.W007` | challenge `expires_seconds` outside 60–3600 |
| `altcha.W008` | vendored JS not found by staticfiles |
| `altcha.W009` | `WIDGET_CHALLENGE_MODE="endpoint"` but URL not wired |
| `altcha.W010` | a deprecated `ALTCHA_*` setting is in use |
| `altcha.W011` | Sentinel remote + retries on the stdlib transport |
| `altcha.W012` | (info) `SENTINEL_VERIFY_FIELDS` on — remember `bind_form_fields` |
| `altcha.W013` | `CHALLENGE_BIND_SESSION` on with a verifier that ignores it (Sentinel, null) |
| `altcha.W014` | `ALTCHA_WIDGET_DEFAULTS` has keys that are not `<altcha-widget>` attributes |
| `altcha.W015` | challenge endpoint disabled while its URL is still wired (route 404s) |
