"""A verifier that accepts everything — for the legacy ``ALTCHA_VERIFICATION_ENABLED=False``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..challenge import build_challenge
from ..conf import conf
from ..results import ErrorCode, PayloadType, VerificationResult
from .base import BaseVerifier

if TYPE_CHECKING:
    from django.http import HttpRequest


class NullVerifier(BaseVerifier):
    """Skips verification entirely. Still enforces "a value was submitted"."""

    name = "null"

    def verify(
        self,
        payload: str,
        *,
        request: HttpRequest | None = None,
        form_data: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        if not payload:
            return VerificationResult.failure(ErrorCode.REQUIRED)
        return VerificationResult.success(payload_type=PayloadType.TEST)

    def get_challenge(self, *, request: HttpRequest | None = None) -> dict:
        # Still emit a real challenge so the browser widget renders normally.
        secret = conf.HMAC_SECRET or "altcha-django-null-verifier"
        return build_challenge(hmac_secret=secret).to_dict()
