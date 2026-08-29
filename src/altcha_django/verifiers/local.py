"""Local (self-hosted) proof-of-work verification — ALTCHA v2 only."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, cast

from altcha import verify_solution

from ..challenge import build_challenge, challenge_id
from ..conf import conf
from ..results import ErrorCode, PayloadType, VerificationResult
from .base import BaseVerifier

if TYPE_CHECKING:
    from django.http import HttpRequest

HmacAlgorithm = Literal["SHA-256", "SHA-384", "SHA-512"]


def _hmac_algo(value: str) -> HmacAlgorithm:
    return cast("HmacAlgorithm", value)


def decode_payload(payload: str) -> dict[str, Any] | None:
    """base64 -> JSON dict, or ``None`` if it is not well-formed."""
    try:
        raw = base64.b64decode(payload, validate=True)
        obj = json.loads(raw)
    except (binascii.Error, ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def is_v1_pow_shape(decoded: Mapping[str, Any]) -> bool:
    return {"algorithm", "challenge", "number", "salt", "signature"} <= set(decoded)


def is_server_signature_shape(decoded: Mapping[str, Any]) -> bool:
    return "verificationData" in decoded


class LocalVerifier(BaseVerifier):
    """Verify a solved v2 challenge with a locally held HMAC secret."""

    name = "local"

    def __init__(
        self,
        *,
        hmac_secret: str | bytes | None = None,
        hmac_key_secret: str | bytes | None = None,
        hmac_algorithm: str | None = None,
        challenge: dict | None = None,
        bind_session: bool | None = None,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.hmac_secret = hmac_secret if hmac_secret is not None else conf.HMAC_SECRET
        self.hmac_key_secret = (
            hmac_key_secret if hmac_key_secret is not None else conf.CHALLENGE_HMAC_KEY_SECRET
        )
        self.hmac_algorithm = hmac_algorithm or conf.HMAC_ALGORITHM
        self.challenge_overrides = challenge or {}
        self.bind_session = conf.CHALLENGE_BIND_SESSION if bind_session is None else bind_session

    # -- challenge ----------------------------------------------------
    def get_challenge(self, *, request: HttpRequest | None = None) -> dict:
        challenge = build_challenge(
            hmac_secret=self.hmac_secret,
            hmac_key_secret=self.hmac_key_secret,
            hmac_algorithm=self.hmac_algorithm,
            bind_session_token=self.bind_session,
            **self.challenge_overrides,
        )
        return challenge.to_dict()

    # -- verification ---------------------------------------------------
    def verify(
        self,
        payload: str,
        *,
        request: HttpRequest | None = None,
        form_data: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        if not payload:
            return VerificationResult.failure(ErrorCode.REQUIRED)
        if not self.hmac_secret:
            return VerificationResult.failure(
                ErrorCode.MISCONFIGURED, error="ALTCHA_HMAC_SECRET is not set"
            )

        decoded = decode_payload(payload)
        if decoded is None:
            return VerificationResult.failure(
                ErrorCode.MALFORMED, error="payload is not valid base64 JSON"
            )
        if is_server_signature_shape(decoded):
            return VerificationResult.failure(
                ErrorCode.MALFORMED,
                error="server-signature payload received by the local verifier "
                "(configure ALTCHA_VERIFIER='sentinel')",
            )
        if is_v1_pow_shape(decoded):
            return VerificationResult.failure(
                ErrorCode.MALFORMED,
                error="ALTCHA proof-of-work v1 payloads are not supported",
                payload_type=PayloadType.UNKNOWN,
            )

        params = (decoded.get("challenge") or {}).get("parameters") or {}
        raw_id = challenge_id(params.get("data")) or params.get("nonce")
        replay_id: str | None = str(raw_id) if raw_id else None
        expires_at = params.get("expiresAt")

        result = verify_solution(
            payload,
            self.hmac_secret,
            hmac_key_secret=self.hmac_key_secret,
            hmac_algorithm=_hmac_algo(self.hmac_algorithm),
        )
        common: dict[str, Any] = {
            "payload_type": PayloadType.POW_V2,
            "replay_id": replay_id,
            "expires_at": int(expires_at) if expires_at else None,
            "duration_ms": result.time,
        }
        if result.verified:
            code, reason = self._session_binding_failure(request, replay_id)
            if code is not None:
                return VerificationResult.failure(code, error=reason, **common)
            return VerificationResult.success(**common)

        if result.expired:
            code = ErrorCode.EXPIRED
        elif result.invalid_signature:
            code = ErrorCode.INVALID_SIGNATURE
        elif result.error:
            code = ErrorCode.MALFORMED
        else:
            code = ErrorCode.INVALID_SOLUTION
        return VerificationResult.failure(code, error=result.error, **common)

    # -- session binding ------------------------------------------------
    def check_session_binding(self, request: HttpRequest | None, replay_id: str | None) -> bool:
        """``True`` if the challenge may be accepted for this session."""
        return self._session_binding_failure(request, replay_id)[0] is None

    def _session_binding_failure(
        self, request: HttpRequest | None, replay_id: str | None
    ) -> tuple[ErrorCode | None, str | None]:
        """Consume the session token, or say why the challenge is not acceptable.

        Fails closed in every branch. A missing request or session means the *project*
        is misconfigured (binding needs ``AltchaMixin`` and ``SessionMiddleware``), and
        is reported as such rather than as a bad solution. A token that is simply
        absent from the session is indistinguishable from one minted for someone else,
        so it stays ``invalid_solution``; ``checks.E006`` catches the configuration
        that makes *every* token absent (challenges minted inline).
        """
        if not self.bind_session:
            return None, None
        if request is None:
            return (
                ErrorCode.MISCONFIGURED,
                "session binding is enabled but the field got no request; add "
                "AltchaMixin to the form and pass request= when instantiating it",
            )
        session = getattr(request, "session", None)
        if session is None:
            return (
                ErrorCode.MISCONFIGURED,
                "session binding is enabled but request.session is unavailable; "
                "enable django.contrib.sessions and SessionMiddleware",
            )
        tokens = list(session.get("altcha_challenges", []))
        if replay_id not in tokens:
            return ErrorCode.INVALID_SOLUTION, "challenge was not issued to this session"
        tokens.remove(replay_id)
        session["altcha_challenges"] = tokens
        return None, None
