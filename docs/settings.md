# Settings reference

All settings are flat `ALTCHA_*` names in your Django settings module.

## Verifier

| Setting | Default | Notes |
|---|---|---|
| `ALTCHA_VERIFIER` | `"local"` | `local` / `sentinel` / `null` / dotted path |
| `ALTCHA_VERIFIER_OPTIONS` | `{}` | kwargs passed to the verifier |

## Local proof-of-work

| Setting | Default |
|---|---|
| `ALTCHA_HMAC_SECRET` | `None` (**required**) |
| `ALTCHA_HMAC_ALGORITHM` | `"SHA-256"` |
| `ALTCHA_CHALLENGE` | `{"algorithm": "PBKDF2/SHA-256", "cost": 5000, "key_prefix": "00", "max_number": None, "expires_seconds": 600, "key_length": 32, "memory_cost": None, "parallelism": None}` (merged over your overrides; `key_prefix` = probabilistic difficulty, set `max_number` for deterministic mode; `memory_cost` is in KiB and applies to `ARGON2ID` / `SCRYPT` only) |
| `ALTCHA_CHALLENGE_HMAC_KEY_SECRET` | `None` |
| `ALTCHA_CHALLENGE_BIND_SESSION` | `False` |

## Challenge endpoint

| Setting | Default |
|---|---|
| `ALTCHA_CHALLENGE_ENDPOINT_ENABLED` | `True` |
| `ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT` | `None` — dotted path to `(request) -> bool` |
| `ALTCHA_TRUSTED_PROXIES` | `[]` — IPs/CIDRs allowed to set `X-Forwarded-For` (see below) |
| `ALTCHA_WIDGET_CHALLENGE_MODE` | `"auto"` — `endpoint` / `inline` / `auto` |

### Client IP behind a proxy

`X-Forwarded-For` can be sent by any client, so it is **ignored by default** and
the rate limiter buckets on `REMOTE_ADDR`. If your app sits behind a load
balancer or reverse proxy, list the proxies so the real client can be recovered:

```python
ALTCHA_TRUSTED_PROXIES = ["10.0.0.0/8", "192.168.1.5", "2001:db8::/32"]
```

The header is then consulted only when the request actually arrived from one of
those addresses, and the chain is walked from the right (nearest hop first) until
an address that is not itself a trusted proxy is found — so a client that prepends
`X-Forwarded-For: 1.2.3.4` cannot impersonate anyone or mint unlimited rate-limit
buckets. Invalid entries are reported by `altcha.E012`.

`altcha_django.ratelimit.client_ip(request)` is public, so a custom
`ALTCHA_CHALLENGE_ENDPOINT_RATELIMIT` gate can reuse the same logic.

## Replay protection

| Setting | Default |
|---|---|
| `ALTCHA_REPLAY_PROTECTION` | `True` |
| `ALTCHA_CACHE_ALIAS` | `"default"` |
| `ALTCHA_REPLAY_KEY_PREFIX` | `"altcha:replay:"` |
| `ALTCHA_REPLAY_FALLBACK_TTL` | `3600` |
| `ALTCHA_REPLAY_CLOCK_SKEW` | `30` |

## Widget

| Setting | Default |
|---|---|
| `ALTCHA_WIDGET_JS_SOURCE` | `"vendored"` — `vendored` / `cdn` / `custom` |
| `ALTCHA_WIDGET_JS_URL` | `None` (required for `custom`) |
| `ALTCHA_WIDGET_JS_CDN` | jsDelivr `altcha@3` |
| `ALTCHA_WIDGET_I18N` | `False` |
| `ALTCHA_WIDGET_I18N_JS_URL` | `None` |
| `ALTCHA_WIDGET_DEFAULTS` | `{"type": "checkbox", "display": "standard"}` |
| `ALTCHA_WIDGET_CONFIGURATION` | `{}` |

## Sentinel (self-hosted)

| Setting | Default | Notes |
|---|---|---|
| `ALTCHA_SENTINEL_CHALLENGE_URL` | `None` | full challenge URL of your instance, API key in the query string |
| `ALTCHA_SENTINEL_API_SECRET` | `None` | API key secret, for local signature verification |
| `ALTCHA_SENTINEL_VERIFY_URL` | `None` | only for `mode="remote"`; derived from the challenge URL when unset |
| `ALTCHA_SENTINEL_MODE` | `"local"` | `local` / `remote` |
| `ALTCHA_SENTINEL_MIN_SCORE` | `None` |
| `ALTCHA_SENTINEL_REJECT_CLASSIFICATIONS` | `["BAD"]` |
| `ALTCHA_SENTINEL_VERIFY_FIELDS` | `True` |
| `ALTCHA_SENTINEL_SPAMFILTER` | `False` |
| `ALTCHA_SENTINEL_PROXY_CHALLENGE` | `False` |
| `ALTCHA_SENTINEL_TIMEOUT` | `10.0` |
| `ALTCHA_SENTINEL_RETRIES` | `1` |
| `ALTCHA_SENTINEL_HTTP_POST` | `None` | dotted path or callable; `"altcha_django.transports.httpx_post"` ships with the `[sentinel]` extra |
| `ALTCHA_SENTINEL_HTTP_GET` | `None` | as above, for challenge fetches; `"altcha_django.transports.httpx_get"` |

## Misc

| Setting | Default |
|---|---|
| `ALTCHA_TEST_MODE` | `False` |
| `ALTCHA_COLLECT_STATS` | `False` |

## Deprecated (still honoured, `altcha.W010`)

`ALTCHA_HMAC_KEY` → `ALTCHA_HMAC_SECRET` ·
`ALTCHA_CHALLENGE_EXPIRE` (ms) → `ALTCHA_CHALLENGE["expires_seconds"]` (s) ·
`ALTCHA_JS_URL` → `ALTCHA_WIDGET_JS_URL` ·
`ALTCHA_JS_TRANSLATIONS_URL` → `ALTCHA_WIDGET_I18N_JS_URL` ·
`ALTCHA_INCLUDE_TRANSLATIONS` → `ALTCHA_WIDGET_I18N` ·
`ALTCHA_VERIFICATION_ENABLED = False` → `ALTCHA_VERIFIER = "null"`
