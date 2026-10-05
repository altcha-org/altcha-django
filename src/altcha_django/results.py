"""Value objects returned by the verification pipeline.

These types are deliberately framework-agnostic: nothing here imports Django, so
the verifier layer can be reused from DRF, management commands, Celery tasks, etc.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator, Mapping
from enum import Enum
from typing import Any


class PayloadType(str, Enum):
    """What kind of ALTCHA payload was verified."""

    POW_V2 = "pow_v2"
    SERVER_SIGNATURE = "server_signature"
    SENTINEL_REMOTE = "sentinel_remote"
    TEST = "test"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # keep f-strings / logging tidy
        return self.value


class Classification(str, Enum):
    """ALTCHA Sentinel classification verdict."""

    GOOD = "GOOD"
    NEUTRAL = "NEUTRAL"
    BAD = "BAD"

    def __str__(self) -> str:
        return self.value


class ErrorCode(str, Enum):
    """Stable failure codes.

    These double as :class:`~django.forms.ValidationError` codes and as
    ``AltchaField.error_messages`` keys, so downstream code can branch on them.
    """

    REQUIRED = "required"
    MALFORMED = "malformed"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_SOLUTION = "invalid_solution"
    EXPIRED = "expired"
    REPLAYED = "replayed"
    UNVERIFIED = "unverified"
    CLASSIFICATION_REJECTED = "classification_rejected"
    SCORE_REJECTED = "score_rejected"
    FIELDS_HASH_MISMATCH = "fields_hash_mismatch"
    BACKEND_ERROR = "backend_error"
    MISCONFIGURED = "misconfigured"

    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass(frozen=True, slots=True)
class VerificationResult:
    """Outcome of verifying a single ALTCHA payload.

    Instances are immutable; use :func:`dataclasses.replace` to derive a modified
    copy (the pipeline does this when it downgrades a result to ``replayed``).
    """

    verified: bool
    code: str | None = None
    error: str | None = None
    payload_type: PayloadType = PayloadType.UNKNOWN
    replay_id: str | None = None
    expires_at: int | None = None
    score: float | None = None
    classification: str | None = None
    verification_data: dict | None = None
    duration_ms: float | None = None

    @classmethod
    def success(cls, **kwargs: object) -> VerificationResult:
        kwargs.pop("verified", None)
        kwargs.pop("code", None)
        return cls(verified=True, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def failure(cls, code: object, **kwargs: object) -> VerificationResult:
        kwargs.pop("verified", None)
        return cls(verified=False, code=str(code), **kwargs)  # type: ignore[arg-type]

    @property
    def ok(self) -> bool:
        """Alias for :attr:`verified`, for readability at call sites."""
        return self.verified


class BoundFormData(Mapping[str, Any]):
    """The fields an ``AltchaField`` binds, keyed by HTML ``name`` (form prefix
    included, as the widget reports them to Sentinel).

    As a mapping it holds only the bound fields: those are the ones whose values
    must be covered by Sentinel's ``fieldsHash``. :meth:`value` reads any field of
    the submission, because the widget also hashes text inputs that are not bound.
    """

    __slots__ = ("_bound", "_submitted")

    def __init__(self, names: Iterable[str], submitted: Mapping[str, Any]) -> None:
        self._submitted = submitted
        self._bound = {name: submitted.get(name, "") for name in names}

    def __getitem__(self, name: str) -> Any:
        return self._bound[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._bound)

    def __len__(self) -> int:
        return len(self._bound)

    def value(self, name: str) -> Any:
        """The submitted value of ``name`` (bound or not), ``""`` if absent."""
        return self._submitted.get(name, "")
