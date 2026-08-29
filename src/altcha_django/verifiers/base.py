"""The verifier contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async

from ..results import PayloadType, VerificationResult

if TYPE_CHECKING:
    from django.core.checks import CheckMessage
    from django.http import HttpRequest


class BaseVerifier:
    """Base class for verification backends.

    Subclasses must implement :meth:`verify`. Everything else has a working
    default: :meth:`averify` / :meth:`aget_challenge` wrap the sync methods in a
    thread, :meth:`get_challenge` and :meth:`get_widget_challenge_ref` are only
    needed by backends that issue their own challenges.
    """

    #: short identifier, used as the signal ``sender`` label and replay-cache scope
    name: str = "base"

    def __init__(self, **options: Any) -> None:
        self.options = options

    # -- verification ---------------------------------------------------
    def verify(
        self,
        payload: str,
        *,
        request: HttpRequest | None = None,
        form_data: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        raise NotImplementedError

    async def averify(
        self,
        payload: str,
        *,
        request: HttpRequest | None = None,
        form_data: Mapping[str, Any] | None = None,
    ) -> VerificationResult:
        return await sync_to_async(self.verify, thread_sensitive=True)(
            payload, request=request, form_data=form_data
        )

    # -- challenge issuance ------------------------------------------
    def get_challenge(self, *, request: HttpRequest | None = None) -> dict:
        """Return a JSON-serialisable challenge for inline mode / the challenge view."""
        raise NotImplementedError(f"{type(self).__name__} does not issue challenges directly.")

    async def aget_challenge(self, *, request: HttpRequest | None = None) -> dict:
        return await sync_to_async(self.get_challenge, thread_sensitive=False)(request=request)

    def get_widget_challenge_ref(self, *, request: HttpRequest | None = None) -> str | None:
        """URL to place in the widget ``challenge`` attribute, or ``None``.

        ``None`` means "let the field decide" (explicit ``challenge_url``, the
        bundled challenge view, or an inline challenge).
        """
        return None

    # -- test mode ----------------------------------------------------
    def verify_test_payload(self, payload: str) -> VerificationResult | None:
        """Return a success result for a recognised test token, else ``None``."""
        if payload:
            return VerificationResult.success(payload_type=PayloadType.TEST)
        return None

    # -- system checks ------------------------------------------------
    def check(self, **kwargs: Any) -> list[CheckMessage]:
        return []
