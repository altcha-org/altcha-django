"""Challenge endpoints.

Wiring these is optional (``path("altcha/", include("altcha_django.urls"))``). When
they are absent the widget mints challenges inline; ``checks.W009`` points this out.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils.cache import patch_vary_headers
from django.utils.module_loading import import_string
from django.views.generic import View

from .challenge import challenge_id
from .conf import conf
from .verifiers import get_verifier
from .verifiers.sentinel import SentinelVerifier

_SESSION_KEY = "altcha_challenges"
_SESSION_MAX = 32


def _client_challenge_bind(request: HttpRequest, challenge: dict) -> None:
    token = challenge_id((challenge.get("parameters") or {}).get("data"))
    if not token:
        return
    tokens = list(request.session.get(_SESSION_KEY, []))
    tokens.append(token)
    request.session[_SESSION_KEY] = tokens[-_SESSION_MAX:]


def _ratelimit_ok(request: HttpRequest, override: Any) -> bool:
    fn = override
    if fn is None and conf.CHALLENGE_ENDPOINT_RATELIMIT:
        fn = import_string(conf.CHALLENGE_ENDPOINT_RATELIMIT)
    if fn is None:
        return True
    return bool(fn(request))


class ChallengeView(View):
    """``GET`` -> a fresh, signed ALTCHA v2 challenge as JSON."""

    # No decorator: ``View`` 405s other methods itself, and (unlike the sync
    # ``require_safe`` wrapper) does so correctly for the async subclass too.
    http_method_names = ["get", "head", "options"]

    verifier_alias: str | None = None
    ratelimit: Any = None

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not conf.CHALLENGE_ENDPOINT_ENABLED:
            raise Http404
        if not _ratelimit_ok(request, self.ratelimit):
            return HttpResponse(status=429, headers={"Retry-After": "60"})

        verifier = get_verifier(self.verifier_alias)
        challenge = verifier.get_challenge(request=request)
        if conf.CHALLENGE_BIND_SESSION:
            _client_challenge_bind(request, challenge)

        response = JsonResponse(challenge)
        response["Cache-Control"] = "no-store"
        patch_vary_headers(response, ("Cookie",))
        return response


class AsyncChallengeView(ChallengeView):
    """Async variant — keeps the PBKDF2 work off the event loop."""

    async def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:  # type: ignore[override]
        from asgiref.sync import sync_to_async

        if not conf.CHALLENGE_ENDPOINT_ENABLED:
            raise Http404
        if not await sync_to_async(_ratelimit_ok)(request, self.ratelimit):
            return HttpResponse(status=429, headers={"Retry-After": "60"})

        verifier = get_verifier(self.verifier_alias)
        challenge = await verifier.aget_challenge(request=request)
        if conf.CHALLENGE_BIND_SESSION:
            await sync_to_async(_client_challenge_bind)(request, challenge)

        response = JsonResponse(challenge)
        response["Cache-Control"] = "no-store"
        patch_vary_headers(response, ("Cookie",))
        return response


class SentinelChallengeProxyView(View):
    """Same-origin proxy for the Sentinel challenge endpoint.

    Fetches ``ALTCHA_SENTINEL_CHALLENGE_URL`` server-side and returns it under
    your own origin, so the browser makes no cross-origin request (and you can
    add caching / rate-limiting here). The response body is relayed as-is,
    including any ``configuration`` Sentinel sends for the widget. Only
    reachable when ``ALTCHA_SENTINEL_PROXY_CHALLENGE=True``.
    """

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not conf.SENTINEL_PROXY_CHALLENGE:
            raise Http404
        verifier = get_verifier("sentinel")
        if not isinstance(verifier, SentinelVerifier):  # pragma: no cover - misconfig
            raise Http404
        challenge = verifier.get_challenge(request=request)
        response = JsonResponse(challenge)
        response["Cache-Control"] = "no-store"
        return response
