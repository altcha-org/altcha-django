# Local (self-hosted) verification

The default backend (`ALTCHA_VERIFIER = "local"`) issues and verifies
proof-of-work v2 challenges with a locally held HMAC secret. No external service
is contacted.

## Difficulty: probabilistic vs deterministic

The mode is selected by the parameters, exactly as in the `altcha` library:

**Probabilistic** (default) — the client brute-forces a counter until the derived
key's hex starts with `key_prefix`. 

**Deterministic** — set `max_number`. The server picks a secret `counter` in
`[max_number // 2, max_number)` and embeds the real key prefix, so the client
must find that exact value. Work is **bounded** (`< max_number` KDF evaluations,
≈ `0.75 * max_number` on average) with predictable solve times, and the server
verifies with a single re-derivation — or a single HMAC compare when
`ALTCHA_CHALLENGE_HMAC_KEY_SECRET` is set (see below). This is what the official
`altcha-lib` server example does.

Each KDF evaluation runs `cost` iterations, spread across the browser's PoW
workers.

## Challenge tuning

```python
ALTCHA_CHALLENGE = {
    "algorithm": "PBKDF2/SHA-256",   # or SHA-256, SCRYPT, ARGON2ID
    "cost": 5000,                    # KDF iterations per counter attempt
    "key_prefix": "00",              # probabilistic difficulty (hex); longer = harder
    "max_number": None,              # set an int -> deterministic mode (counter bound)
    "expires_seconds": 600,          # challenge lifetime + replay-cache TTL
    "key_length": 32,
}
```

Settings that would let a challenge be solved without real work are rejected when
a challenge is issued and by `manage.py check` (`altcha.E010`, `altcha.E013`):

- `key_prefix` must be non-empty hex, at most `2 * key_length` characters
  (probabilistic mode). An empty prefix is matched by any counter.
- `key_length` must be at least 16 bytes. In deterministic mode half of the derived
  key is published as the prefix.
- For `SHA-256`, `SHA-384` and `SHA-512`, `key_length` must not exceed the digest
  size (32, 48, 64). These KDFs return a single digest, so a longer `key_length`
  would publish the whole key, which `ALTCHA_CHALLENGE_HMAC_KEY_SECRET` then
  accepts with no work.
- `cost`, `key_length`, `expires_seconds` and, when set, `max_number`,
  `memory_cost` and `parallelism` must be positive integers.

`max_number` below 1000 is allowed but warned about (`altcha.W016`): the client
finds the counter after at most `max_number` KDF evaluations.

`ARGON2ID` requires `pip install 'altcha-django[argon2]'`.

## How verification works

`AltchaField.clean()` calls `run_verification()`, which:

1. rejects an empty submission with `code="required"` (no signal);
2. runs `altcha.verify_solution()` against `ALTCHA_HMAC_SECRET`
   (checks expiry → challenge signature → solution);
3. on success, atomically claims the challenge `nonce` in the cache — a second
   submission of the same payload fails with `code="replayed"`;
4. fires `altcha_verified` / `altcha_verification_failed` / `altcha_replayed`.

## Proof-of-Work v1

v1-shaped payloads are **rejected** (`code="malformed"`). This library only
issues and accepts v2.

## Fast verification path

Set `ALTCHA_CHALLENGE_HMAC_KEY_SECRET` to also HMAC the derived key when issuing
challenges; verification then compares that HMAC instead of re-deriving the key.
Recommended for high request rates.

## Session binding (defence in depth)

```python
ALTCHA_CHALLENGE_BIND_SESSION = True
ALTCHA_VERIFIER_OPTIONS = {"bind_session": True}
```

Each issued challenge carries a random `id` under `parameters.data` — the same
key ALTCHA Sentinel uses, so both backends are read the same way. The challenge
view stores it in the session and the verifier requires it back, so a challenge
minted for one session can't be solved for another.

Binding is recorded **only** when the challenge comes from the bundled endpoint,
so it has three requirements — `manage.py check` enforces all of them:

1. the challenge URLs are wired and the widget uses them (`ALTCHA_WIDGET_CHALLENGE_MODE`
   of `"endpoint"`, or `"auto"` with the URLs included). Inline challenges are never
   bound, so `"inline"` mode is rejected with `altcha.E006`;
2. `django.contrib.sessions` and `SessionMiddleware` are enabled (`altcha.E011`);
3. every form using `AltchaField` mixes in `AltchaMixin` **and** is instantiated with
   `request=` — without the request the field cannot read the session and fails closed.

A verification that trips 2 or 3 fails with `code="misconfigured"` and an
explanatory `result.error`, distinct from the `code="invalid_solution"` you get when
a token genuinely does not belong to the session.
