# Testing

`altcha-django` never mocks crypto in its own suite — it builds real payloads
with `altcha.solve_challenge` at a tiny `cost`, and real Sentinel signatures as
the exact inverse of `altcha.verify_server_signature`. Do the same in your tests.

## Bypass in tests

```python
@override_settings(ALTCHA_TEST_MODE=True)
def test_signup(self):
    resp = self.client.post("/signup/", {..., "altcha": "x"})
```

`ALTCHA_TEST_MODE` makes `run_verification` accept any non-empty payload (and
skips replay). The widget also sets `"test": true` in its `configuration` JSON
so the browser widget mocks a successful verification instead of doing real
proof-of-work. `altcha.W004` warns if this is on without `DEBUG`.

## Real payloads

```python
import datetime as dt
from altcha import Payload, create_challenge, solve_challenge

def make_altcha_payload(secret, cost=200):
    c = create_challenge(
        "PBKDF2/SHA-256", cost,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
        hmac_secret=secret,
    )
    return Payload(c, solve_challenge(c)).to_base64()
```

See `tests/factories.py` in the repo for expired, tampered, unsigned and Sentinel
variants.

## Running this project's suite

```console
pip install -e '.[dev]'
pytest                 # or: python -m tests.runtests
nox                    # full matrix: Python 3.10-3.14 x Django 4.2-6.1
```
