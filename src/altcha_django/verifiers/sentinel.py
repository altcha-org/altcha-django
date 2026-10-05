"""ALTCHA Sentinel verification.

Sentinel is **self-hosted**. Configuration is just two values:

* ``ALTCHA_SENTINEL_CHALLENGE_URL`` — the full challenge URL of *your* Sentinel
  instance, with the API key already in the query string, e.g.
  ``https://sentinel.example.com/v1/challenge?apiKey=key_...``. This is handed
  straight to the browser widget.
* ``ALTCHA_SENTINEL_API_SECRET`` — the API key's secret, used to verify the
  signed payload locally (``altcha.verify_server_signature``).

``mode="remote"`` instead POSTs the payload to the Sentinel
``/v1/verify/signature`` endpoint (derived from the challenge URL, or set
``ALTCHA_SENTINEL_VERIFY_URL`` explicitly).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from altcha import (
    parse_verification_data,
    verify_fields_hash,
    verify_server,
    verify_server_signature,
)

from ..conf import conf
from ..exceptions import AltchaConfigurationError
from ..results import BoundFormData, ErrorCode, PayloadType, VerificationResult
from .base import BaseVerifier
from .local import decode_payload, is_server_signature_shape

if TYPE_CHECKING:
    from django.http import HttpRequest


def _default_http_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET", headers=headers)  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network
        return exc.code, exc.read()


def _sibling_url(challenge_url: str, target: str) -> str:
    """Derive a sibling endpoint from the challenge URL.

    ``https://host/base/v1/challenge?apiKey=x`` + ``verify/signature``
    -> ``https://host/base/v1/verify/signature`` (query stripped).
    """
    parts = urlsplit(challenge_url)
    path = parts.path
    if not path.rstrip("/").endswith("/challenge"):
        raise AltchaConfigurationError(
            "Cannot derive the Sentinel verify URL from ALTCHA_SENTINEL_CHALLENGE_URL "
            f"({challenge_url!r}); set ALTCHA_SENTINEL_VERIFY_URL explicitly."
        )
    base = path.rstrip("/")[: -len("challenge")]
    return urlunsplit((parts.scheme, parts.netloc, base + target, "", ""))


class SentinelVerifier(BaseVerifier):
    """Verify payloads issued and signed by a self-hosted ALTCHA Sentinel."""

    name = "sentinel"

    def __init__(
        self,
        *,
        challenge_url: str | None = None,
        api_secret: str | None = None,
        verify_url: str | None = None,
        mode: str | None = None,
        min_score: float | None = None,
        reject_classifications: list[str] | None = None,
        verify_fields: bool | None = None,
        spamfilter: bool | None = None,
        proxy_challenge: bool | None = None,
        http_post: Callable[..., tuple[int, bytes]] | None = None,
        http_get: Callable[..., tuple[int, bytes]] | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.challenge_url = (
            challenge_url if challenge_url is not None else conf.SENTINEL_CHALLENGE_URL
        ) or ""
        self.api_secret = api_secret if api_secret is not None else conf.SENTINEL_API_SECRET
        self._verify_url_override = (
            verify_url if verify_url is not None else conf.SENTINEL_VERIFY_URL
        )
        self.mode = (mode or conf.SENTINEL_MODE or "local").lower()
        self.min_score = min_score if min_score is not None else conf.SENTINEL_MIN_SCORE
        self.reject = {
            str(c).upper()
            for c in (
                reject_classifications
                if reject_classifications is not None
                else conf.SENTINEL_REJECT_CLASSIFICATIONS
            )
        }
        self.verify_fields = (
            conf.SENTINEL_VERIFY_FIELDS if verify_fields is None else verify_fields
        )
        self.spamfilter = conf.SENTINEL_SPAMFILTER if spamfilter is None else spamfilter
        self.proxy_challenge = (
            conf.SENTINEL_PROXY_CHALLENGE if proxy_challenge is None else proxy_challenge
        )
        self.http_post = _resolve_callable(
            http_post if http_post is not None else conf.SENTINEL_HTTP_POST
        )
        self.http_get = (
            _resolve_callable(http_get if http_get is not None else conf.SENTINEL_HTTP_GET)
            or _default_http_get
        )
        self.timeout = timeout if timeout is not None else conf.SENTINEL_TIMEOUT
        self.retries = retries if retries is not None else conf.SENTINEL_RETRIES

    # -- derived endpoints -------------------------------------------
    @property
    def verify_url(self) -> str:
        return self._verify_url_override or _sibling_url(self.challenge_url, "verify/signature")

    @property
    def widget_verify_url(self) -> str:
        """The ``/v1/verify`` endpoint the widget POSTs to when the spam filter is on."""
        return _sibling_url(self.challenge_url, "verify")

    # -- challenge --------------------------------------------------
    def get_widget_challenge_ref(self, *, request: HttpRequest | None = None) -> str | None:
        if self.proxy_challenge:
            from django.urls import NoReverseMatch, reverse

            try:
                return reverse("altcha_django:sentinel-challenge")
            except NoReverseMatch:  # pragma: no cover - surfaced by checks
                return self.challenge_url or None
        return self.challenge_url or None

    def get_challenge(self, *, request: HttpRequest | None = None) -> dict[str, Any]:
        """Fetch a challenge from Sentinel.

        Any widget configuration Sentinel wants to apply travels in the response
        body's ``configuration`` property, so returning the parsed JSON verbatim
        is all a same-origin proxy needs to relay.
        """
        if not self.challenge_url:
            raise AltchaConfigurationError("ALTCHA_SENTINEL_CHALLENGE_URL is not set")
        status, body = self.http_get(
            self.challenge_url, {"Accept": "application/json"}, self.timeout
        )
        if not 200 <= status < 300:  # pragma: no cover - network
            raise AltchaConfigurationError(f"Sentinel challenge request failed with HTTP {status}")
        result: dict[str, Any] = json.loads(body)
        return result

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
        decoded = decode_payload(payload)
        if decoded is None:
            return VerificationResult.failure(
                ErrorCode.MALFORMED, error="payload is not valid base64 JSON"
            )
        if not is_server_signature_shape(decoded):
            return VerificationResult.failure(
                ErrorCode.MALFORMED,
                error="expected a Sentinel server-signature payload "
                "(is the widget pointed at Sentinel?)",
            )

        # Covered by the signature, but only trustworthy once that has been checked.
        replay_id = _signed_id(decoded.get("verificationData"))
        if self.mode == "remote":
            return self._verify_remote(payload, form_data, replay_id)
        return self._verify_local(payload, form_data, replay_id)

    # -- local mode -----------------------------------------------------
    def _verify_local(
        self,
        payload: str,
        form_data: Mapping[str, Any] | None,
        replay_id: str | None,
    ) -> VerificationResult:
        if not self.api_secret:
            return VerificationResult.failure(
                ErrorCode.MISCONFIGURED, error="ALTCHA_SENTINEL_API_SECRET is not set"
            )
        # altcha>=2.3.0 rejects an unknown or malformed payload `algorithm` with
        # invalid_signature; it only raises for an empty secret, handled above.
        result = verify_server_signature(payload, self.api_secret)
        if not result.verified:
            if result.expired:
                code = ErrorCode.EXPIRED
            elif result.invalid_signature:
                code = ErrorCode.INVALID_SIGNATURE
            else:
                code = ErrorCode.UNVERIFIED
            return VerificationResult.failure(
                code,
                payload_type=PayloadType.SERVER_SIGNATURE,
                duration_ms=result.time,
            )
        return self._finish(
            result.verification_data or {},
            form_data,
            PayloadType.SERVER_SIGNATURE,
            replay_id=replay_id,
            duration_ms=result.time,
        )

    # -- remote mode ------------------------------------------------
    def _verify_remote(
        self,
        payload: str,
        form_data: Mapping[str, Any] | None,
        replay_id: str | None,
    ) -> VerificationResult:
        result = verify_server(
            payload,
            self.verify_url,
            secret=self.api_secret,
            timeout=self.timeout,
            retries=self.retries,
            http_post=self.http_post,
        )
        if not result.verified:
            reason = (result.reason or "").upper()
            if reason == "PAYLOAD_ALREADY_USED":
                code = ErrorCode.REPLAYED
            elif result.verification_data:
                # Sentinel returned a verdict (e.g. spam) rather than a transport error.
                code = ErrorCode.UNVERIFIED
            else:
                # HTTP 4xx/5xx, network exception, NETWORK_ERROR, empty body, …
                code = ErrorCode.BACKEND_ERROR
            return VerificationResult.failure(
                code, error=result.reason, payload_type=PayloadType.SENTINEL_REMOTE
            )
        # Sentinel has verified the submitted payload's signature, so its signed id is
        # authoritative; the response's verificationData was already type-coerced.
        vd = result.verification_data
        if isinstance(vd, str):
            vd = parse_verification_data(vd) or {}
        return self._finish(
            vd or {},
            form_data,
            PayloadType.SENTINEL_REMOTE,
            replay_id=replay_id,
        )

    # -- shared policy / success --------------------------------------
    def _finish(
        self,
        vd: Mapping[str, Any],
        form_data: Mapping[str, Any] | None,
        payload_type: PayloadType,
        *,
        replay_id: str | None,
        duration_ms: float | None = None,
    ) -> VerificationResult:
        classification = vd.get("classification")
        score = vd.get("score")
        expires_at = _effective_expiry(vd)
        common = {
            "payload_type": payload_type,
            "replay_id": replay_id,
            "expires_at": expires_at,
            "score": score,
            "classification": classification,
            "verification_data": dict(vd),
            "duration_ms": duration_ms,
        }
        if expires_at is None:
            return VerificationResult.failure(
                ErrorCode.MALFORMED,
                error="payload has neither a signed expire nor a signed time; "
                "its age cannot be bounded",
                **common,
            )
        if expires_at < int(time.time()):
            return VerificationResult.failure(ErrorCode.EXPIRED, **common)
        if classification and str(classification).upper() in self.reject:
            return VerificationResult.failure(ErrorCode.CLASSIFICATION_REJECTED, **common)
        if self.min_score is not None and (score is None or score < self.min_score):
            return VerificationResult.failure(ErrorCode.SCORE_REJECTED, **common)

        if self.verify_fields:
            error = self._fields_binding_error(vd, form_data)
            if error is not None:
                return VerificationResult.failure(
                    ErrorCode.FIELDS_HASH_MISMATCH, error=error, **common
                )

        return VerificationResult.success(**common)

    def _fields_binding_error(
        self, vd: Mapping[str, Any], form_data: Mapping[str, Any] | None
    ) -> str | None:
        """Why the submitted fields are not the ones Sentinel classified, or ``None``.

        ``fields`` / ``fieldsHash`` are whatever the client sent to Sentinel, so their
        absence proves nothing: every bound field that was submitted non-empty must be
        covered by the signed hash. Empty values are exempt because the widget never
        sends them for classification.
        """
        fields_hash = vd.get("fieldsHash")
        if form_data is None:
            if not fields_hash:
                return None
            return (
                "fieldsHash present but no form data was bound; use "
                "AltchaMixin and AltchaField(bind_form_fields=[...])"
            )
        fields = [str(f) for f in (vd.get("fields") or [])]
        submitted = [name for name, value in form_data.items() if value not in (None, "")]
        unsigned = [name for name in submitted if name not in fields]
        if unsigned and not fields_hash:
            hint = "" if self.spamfilter else " (ALTCHA_SENTINEL_SPAMFILTER is off)"
            return f"no fieldsHash; bound fields were not classified{hint}: {', '.join(unsigned)}"
        if unsigned:
            return f"bound fields missing from the signed fields: {', '.join(unsigned)}"
        if not fields_hash:
            return None
        # The widget hashes every non-empty text input, bound or not, by HTML name.
        lookup = form_data.value if isinstance(form_data, BoundFormData) else form_data.get
        values = {name: _text(lookup(name)) for name in fields}
        # Sentinel always hashes field values with SHA-256, whatever digest signed the
        # payload; the payload's unsigned ``algorithm`` must not select it.
        if not verify_fields_hash(values, fields, str(fields_hash), "SHA-256"):
            return "fieldsHash does not match the submitted values"
        return None


def _resolve_callable(value: str | Callable[..., Any] | None) -> Callable[..., Any] | None:
    """Accept a callable, a dotted path to one, or ``None``."""
    if value is None or callable(value):
        return value
    from django.utils.module_loading import import_string

    resolved: Callable[..., Any] = import_string(value)
    return resolved


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _signed_id(verification_data: object) -> str | None:
    """The first ``id`` in the raw signed ``verificationData`` query string.

    Read verbatim (like ``URLSearchParams.get``): ``parse_verification_data`` turns
    ``0123`` into ``123``, ``1.10`` into ``1.1``, strips whitespace and makes ``0``
    falsy, so distinct signed ids would share one replay key.
    """
    if not isinstance(verification_data, str):
        return None
    values = parse_qs(verification_data, keep_blank_values=True).get("id")
    return values[0] if values and values[0] else None


def _timestamp(value: object) -> int | None:
    """A positive int (as ``parse_verification_data`` yields for digits), else ``None``."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _effective_expiry(vd: Mapping[str, Any]) -> int | None:
    """Unix time after which verified Sentinel data must be refused, or ``None``.

    A signed ``expire`` wins. Without one the payload would never expire, yet its
    replay entry lasts only ``ALTCHA_REPLAY_FALLBACK_TTL``; after that it could be
    accepted again. So it is treated as expiring ``REPLAY_FALLBACK_TTL`` seconds
    after its signed ``time``, and the replay entry (TTL derived from
    ``expires_at``) outlives that window. ``None`` means neither field is present,
    so the age cannot be bounded at all.
    """
    expire = _timestamp(vd.get("expire"))
    if expire is not None:
        return expire
    issued = _timestamp(vd.get("time"))
    if issued is not None:
        return issued + int(conf.REPLAY_FALLBACK_TTL)
    return None
