"""Helpers that build *real* ALTCHA payloads for tests (no mocking)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

from altcha import Payload, create_challenge, solve_challenge

# Tiny bound so solve_challenge() stays fast: deterministic counter in [20, 40).
FAST_CHALLENGE = {"algorithm": "PBKDF2/SHA-256", "cost": 50, "max_number": 40}
DEFAULT_SECRET = "test-hmac-secret"


def _pick_counter(cfg):
    hi = cfg.get("max_number")
    if hi is None:
        return None
    lo = max(0, hi // 2)
    return lo + secrets.randbelow(max(1, hi - lo))


# --------------------------------------------------------------------------- #
# Proof-of-work v2
# --------------------------------------------------------------------------- #
def _challenge(secret, *, expires_at=None, expires_in=600, data=None, **overrides):
    cfg = {**FAST_CHALLENGE, **overrides}
    if expires_at is None:
        expires_at = dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(seconds=expires_in)
    return create_challenge(
        cfg["algorithm"],
        cfg["cost"],
        counter=_pick_counter(cfg),
        key_prefix=cfg.get("key_prefix", "00"),
        expires_at=expires_at,
        data=data,
        hmac_secret=secret,
    )


def make_pow_payload(secret=DEFAULT_SECRET, *, expires_in=600, data=None, **overrides) -> str:
    challenge = _challenge(secret, expires_in=expires_in, data=data, **overrides)
    solution = solve_challenge(challenge)
    assert solution is not None, "challenge should be solvable at test cost"
    return Payload(challenge, solution).to_base64()


def make_probabilistic_pow_payload(secret=DEFAULT_SECRET, *, key_prefix="00") -> str:
    """A challenge with no ``max_number`` -> probabilistic mode (uses ``key_prefix``)."""
    return make_pow_payload(secret, max_number=None, key_prefix=key_prefix)


def make_expired_pow_payload(secret=DEFAULT_SECRET) -> str:
    past = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(seconds=30)
    challenge = _challenge(secret, expires_at=past)
    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def make_unsigned_pow_payload() -> str:
    challenge = create_challenge(
        FAST_CHALLENGE["algorithm"],
        FAST_CHALLENGE["cost"],
        counter=_pick_counter(FAST_CHALLENGE),
        expires_at=dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(seconds=600),
        hmac_secret=None,
    )
    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def make_tampered_pow_payload(secret=DEFAULT_SECRET) -> str:
    """A payload whose challenge signature no longer matches its parameters."""
    raw = json.loads(base64.b64decode(make_pow_payload(secret)))
    raw["challenge"]["parameters"]["cost"] += 1  # invalidates the signature
    return base64.b64encode(json.dumps(raw).encode()).decode()


def make_wrong_solution_payload(secret=DEFAULT_SECRET) -> str:
    raw = json.loads(base64.b64decode(make_pow_payload(secret)))
    raw["solution"]["counter"] = raw["solution"]["counter"] + 100000
    return base64.b64encode(json.dumps(raw).encode()).decode()


def make_v1_shaped_payload() -> str:
    obj = {
        "algorithm": "SHA-256",
        "challenge": "deadbeef",
        "number": 12345,
        "salt": "abc123?expires=9999999999",
        "signature": "cafebabe",
        "took": 42,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()


def make_garbage_payload() -> str:
    return "not-base64-!!!"


# --------------------------------------------------------------------------- #
# Sentinel server-signature payloads
# --------------------------------------------------------------------------- #
def _digest(algorithm: str):
    """hashlib constructor for an ALTCHA algorithm name ('SHA-512' -> sha512)."""
    return lambda data=b"": hashlib.new(algorithm.lower().replace("-", ""), data)


def _sign_verification_data(vd_query: str, secret: str, algorithm: str = "SHA-256") -> str:
    # Sentinel hashes verificationData with `algorithm`, then HMAC-SHA256s the digest.
    data_hash = _digest(algorithm)(vd_query.encode()).digest()
    return hmac.new(secret.encode(), data_hash, hashlib.sha256).hexdigest()


def make_sentinel_payload(
    secret=DEFAULT_SECRET,
    *,
    verified=True,
    classification="GOOD",
    score=0.1,
    expire_in=600,
    verification_id=None,
    fields=None,
    field_values=None,
    reasons=None,
    extra=None,
    bad_signature=False,
    algorithm="SHA-256",
) -> str:
    verification_id = verification_id or secrets.token_hex(8)
    pairs: list[tuple[str, str]] = [
        ("verified", "true" if verified else "false"),
        ("score", str(score)),
        ("classification", classification),
        ("expire", str(int(time.time()) + expire_in)),
        ("time", str(int(time.time()))),
        ("id", verification_id),
    ]
    if reasons:
        pairs.append(("reasons", ",".join(reasons)))
    if fields:
        pairs.append(("fields", ",".join(fields)))
        joined = "\n".join(str((field_values or {}).get(name, "")) for name in fields)
        pairs.append(("fieldsHash", _digest(algorithm)(joined.encode()).hexdigest()))
    for key, value in (extra or {}).items():
        pairs.append((key, str(value)))

    vd_query = urlencode(pairs)
    signature = _sign_verification_data(vd_query, secret, algorithm)
    if bad_signature:
        signature = "0" * len(signature)

    obj = {
        "algorithm": algorithm,
        "signature": signature,
        "verificationData": vd_query,
        "verified": verified,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()
