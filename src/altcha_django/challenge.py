"""Challenge construction for local (self-hosted) proof-of-work.

Thin wrapper around :func:`altcha.create_challenge` that applies altcha-django's
defaults and always signs the challenge (an unsigned challenge is rejected by
:func:`altcha.verify_solution`).

Two modes, selected by the parameters (exactly as in the ``altcha`` library):

* **probabilistic** (default) — the client must find *any* counter whose derived
  key hex starts with ``key_prefix`` (default ``"00"`` ≈ 256 expected tries; make
  it longer for more work).
* **deterministic** — set ``max_number``; the server picks a secret ``counter``
  in ``[max_number // 2, max_number)`` and embeds the real key prefix, so the
  client must find that exact counter. Bounds the work at ``< max_number`` KDF
  evaluations, keeps solve times predictable, and lets the server verify with a
  single re-derivation (or a single HMAC compare when ``hmac_key_secret`` is set).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import secrets
import string
from typing import Any, Literal, cast

from altcha import Challenge, create_challenge

from .conf import conf
from .exceptions import AltchaConfigurationError

_KNOWN_ALGORITHMS = frozenset(
    {
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "PBKDF2/SHA-256",
        "PBKDF2/SHA-384",
        "PBKDF2/SHA-512",
        "SCRYPT",
        "ARGON2ID",
    }
)
_HEX = set(string.hexdigits)

#: Key under ``parameters.data`` holding the challenge's unique id. Matches what
#: ALTCHA Sentinel emits, so both backends can be read the same way.
CHALLENGE_ID_KEY = "id"


def challenge_id(data: dict | None) -> str | None:
    """Return the challenge id from a ``parameters.data`` mapping, if present."""
    value = (data or {}).get(CHALLENGE_ID_KEY)
    return str(value) if value else None


@dataclasses.dataclass(slots=True)
class ChallengeConfig:
    """Resolved parameters for a single challenge."""

    algorithm: str = "PBKDF2/SHA-256"
    cost: int = 5000
    #: Probabilistic difficulty: hex prefix the derived key must start with.
    #: Ignored when ``max_number`` selects deterministic mode.
    key_prefix: str = "00"
    #: Set to switch to deterministic mode: the counter upper bound. ``None``
    #: keeps probabilistic mode.
    max_number: int | None = None
    expires_seconds: int = 600
    key_length: int = 32
    #: Memory cost in KiB — Argon2id / scrypt only.
    memory_cost: int | None = None
    parallelism: int | None = None

    @property
    def deterministic(self) -> bool:
        return self.max_number is not None

    @classmethod
    def from_settings(cls, **overrides: Any) -> ChallengeConfig:
        data = {**conf.CHALLENGE, **{k: v for k, v in overrides.items() if v is not None}}
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise AltchaConfigurationError(
                f"Unknown ALTCHA_CHALLENGE keys: {', '.join(sorted(unknown))}"
            )
        return cls(**data)

    def pick_counter(self) -> int | None:
        """A random counter in ``[max_number // 2, max_number)`` for deterministic
        mode, or ``None`` for probabilistic mode."""
        if self.max_number is None:
            return None
        hi = int(self.max_number)
        lo = max(0, hi // 2)
        span = max(1, hi - lo)
        return lo + secrets.randbelow(span)

    def validate(self) -> None:
        if self.algorithm not in _KNOWN_ALGORITHMS:
            raise AltchaConfigurationError(
                f"Unknown challenge algorithm {self.algorithm!r}. "
                f"Expected one of: {', '.join(sorted(_KNOWN_ALGORITHMS))}."
            )
        if self.cost < 1:
            raise AltchaConfigurationError("Challenge 'cost' must be >= 1.")
        if not self.deterministic and set(self.key_prefix) - _HEX:
            raise AltchaConfigurationError(
                f"Challenge 'key_prefix' must be hex; got {self.key_prefix!r}. "
                "A non-hex prefix makes the challenge unsolvable."
            )
        if self.expires_seconds < 1:
            raise AltchaConfigurationError("Challenge 'expires_seconds' must be >= 1.")


def get_challenge_config(**overrides: Any) -> ChallengeConfig:
    """Return the effective :class:`ChallengeConfig` (settings + per-call overrides)."""
    cfg = ChallengeConfig.from_settings(**overrides)
    cfg.validate()
    return cfg


def build_challenge(
    *,
    hmac_secret: str | bytes | None = None,
    hmac_key_secret: str | bytes | None = None,
    hmac_algorithm: str | None = None,
    expires_at: _dt.datetime | int | None = None,
    data: dict | None = None,
    counter: int | None = None,
    bind_session_token: bool = False,
    config: ChallengeConfig | None = None,
    **config_overrides: Any,
) -> Challenge:
    """Create a signed ALTCHA v2 challenge.

    ``data`` is embedded verbatim into ``challenge.parameters.data``. When
    ``bind_session_token`` is true a random ``id`` is added to ``data``
    (used by the challenge view for session binding and as the replay id). Pass an
    explicit ``counter`` to force deterministic mode with that exact value.
    """
    cfg = config or get_challenge_config(**config_overrides)
    cfg.validate()

    secret = hmac_secret if hmac_secret is not None else conf.HMAC_SECRET
    if not secret:
        raise AltchaConfigurationError(
            "Local ALTCHA challenges require a signing secret. Set ALTCHA_HMAC_SECRET."
        )

    if expires_at is None:
        expires_at = _dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(
            seconds=cfg.expires_seconds
        )

    payload_data = dict(data or {})
    if bind_session_token and not challenge_id(payload_data):
        payload_data[CHALLENGE_ID_KEY] = secrets.token_urlsafe(16)

    if counter is None:
        counter = cfg.pick_counter()

    return create_challenge(
        cfg.algorithm,
        cfg.cost,
        counter=counter,  # None -> probabilistic (uses key_prefix)
        key_prefix=cfg.key_prefix,  # overwritten by create_challenge when counter is set
        key_length=cfg.key_length,
        memory_cost=cfg.memory_cost,
        parallelism=cfg.parallelism,
        expires_at=expires_at,
        data=payload_data or None,
        hmac_secret=secret,
        hmac_key_secret=(
            hmac_key_secret if hmac_key_secret is not None else conf.CHALLENGE_HMAC_KEY_SECRET
        ),
        hmac_algorithm=cast(
            'Literal["SHA-256", "SHA-384", "SHA-512"]',
            hmac_algorithm or conf.HMAC_ALGORITHM,
        ),
    )


def challenge_to_dict(challenge: Challenge) -> dict[str, Any]:
    """JSON-serialisable form accepted by the widget's ``challenge`` attribute."""
    return challenge.to_dict()
