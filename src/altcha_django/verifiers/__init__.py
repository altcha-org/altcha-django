"""Verifier registry and the verification pipeline.

``run_verification`` / ``run_averification`` are the single choke point where the
selected backend runs, replay protection is enforced and signals fire. Forms, DRF
and ad-hoc callers all go through here so behaviour is identical everywhere.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string

from ..conf import conf
from ..exceptions import AltchaConfigurationError
from ..results import ErrorCode, VerificationResult
from ..signals import altcha_replayed, altcha_verification_failed, altcha_verified
from .base import BaseVerifier
from .local import LocalVerifier
from .null import NullVerifier
from .sentinel import SentinelVerifier

if TYPE_CHECKING:
    from django.http import HttpRequest

__all__ = [
    "BaseVerifier",
    "LocalVerifier",
    "NullVerifier",
    "SentinelVerifier",
    "get_verifier",
    "register_verifier",
    "run_averification",
    "run_verification",
]

_REGISTRY: dict[str, type[BaseVerifier]] = {
    "local": LocalVerifier,
    "sentinel": SentinelVerifier,
    "null": NullVerifier,
}
_INSTANCES: dict[str, BaseVerifier] = {}


def register_verifier(name: str, cls: type[BaseVerifier]) -> None:
    """Register a verifier under a short alias usable in ``ALTCHA_VERIFIER``."""
    if not (isinstance(cls, type) and issubclass(cls, BaseVerifier)):
        raise TypeError("verifier class must subclass BaseVerifier")
    _REGISTRY[name] = cls
    _INSTANCES.pop(name, None)


def _load_class(alias: str) -> type[BaseVerifier]:
    if alias in _REGISTRY:
        return _REGISTRY[alias]
    try:
        cls = import_string(alias)
    except ImportError as exc:
        raise AltchaConfigurationError(
            f"ALTCHA_VERIFIER={alias!r} is neither a known alias "
            f"({', '.join(sorted(_REGISTRY))}) nor an importable dotted path."
        ) from exc
    if not (isinstance(cls, type) and issubclass(cls, BaseVerifier)):
        raise AltchaConfigurationError(f"{alias!r} does not resolve to a BaseVerifier subclass")
    return cls


def get_verifier(verifier: str | None = None) -> BaseVerifier:
    """Return a (cached) verifier instance for an alias / dotted path."""
    alias = verifier or conf.VERIFIER
    if alias not in _INSTANCES:
        _INSTANCES[alias] = _load_class(alias)(**conf.VERIFIER_OPTIONS)
    return _INSTANCES[alias]


def resolve_verifier(verifier: Any = None) -> BaseVerifier:
    """Accept ``None`` / alias / dotted path / instance / subclass -> instance."""
    if verifier is None or isinstance(verifier, str):
        return get_verifier(verifier)
    if isinstance(verifier, BaseVerifier):
        return verifier
    if isinstance(verifier, type) and issubclass(verifier, BaseVerifier):
        return verifier(**conf.VERIFIER_OPTIONS)
    raise TypeError(f"Cannot resolve verifier from {verifier!r}")


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _enforce_replay(result: VerificationResult, scope: str) -> VerificationResult:
    if not result.verified or not result.replay_id:
        return result
    from ..replay import ReplayProtector

    first_use = ReplayProtector().register(
        result.replay_id, expires_at=result.expires_at, scope=scope
    )
    if first_use:
        return result
    return dataclasses.replace(result, verified=False, code=ErrorCode.REPLAYED.value)


def _emit(
    result: VerificationResult,
    *,
    verifier: BaseVerifier,
    request: HttpRequest | None,
    payload: str,
) -> None:
    sender = type(verifier)
    kw = {"result": result, "verifier": verifier, "request": request, "payload": payload}
    if result.verified:
        altcha_verified.send(sender=sender, **kw)
        return
    if result.code == ErrorCode.REPLAYED.value:
        altcha_replayed.send(sender=sender, replay_id=result.replay_id, **kw)
    altcha_verification_failed.send(sender=sender, code=result.code, **kw)


def run_verification(
    payload: str,
    *,
    verifier: Any = None,
    request: HttpRequest | None = None,
    form_data: Mapping[str, Any] | None = None,
    replay: bool | None = None,
    test_mode: bool | None = None,
) -> VerificationResult:
    """Verify ``payload`` and return a :class:`VerificationResult` (never raises for
    ordinary verification failures)."""
    if not payload:
        # "user submitted nothing" — no backend call and no signal.
        return VerificationResult.failure(ErrorCode.REQUIRED)

    v = resolve_verifier(verifier)
    use_replay = conf.REPLAY_PROTECTION if replay is None else replay
    use_test = conf.TEST_MODE if test_mode is None else test_mode

    if use_test:
        test_result = v.verify_test_payload(payload)
        if test_result is not None:
            _emit(test_result, verifier=v, request=request, payload=payload)
            return test_result

    result = v.verify(payload, request=request, form_data=form_data)
    if use_replay:
        result = _enforce_replay(result, v.name)
    _emit(result, verifier=v, request=request, payload=payload)
    return result


async def run_averification(
    payload: str,
    *,
    verifier: Any = None,
    request: HttpRequest | None = None,
    form_data: Mapping[str, Any] | None = None,
    replay: bool | None = None,
    test_mode: bool | None = None,
) -> VerificationResult:
    """Async twin of :func:`run_verification`."""
    if not payload:
        return VerificationResult.failure(ErrorCode.REQUIRED)

    v = resolve_verifier(verifier)
    use_replay = conf.REPLAY_PROTECTION if replay is None else replay
    use_test = conf.TEST_MODE if test_mode is None else test_mode

    if use_test:
        test_result = v.verify_test_payload(payload)
        if test_result is not None:
            await sync_to_async(_emit)(test_result, verifier=v, request=request, payload=payload)
            return test_result

    result = await v.averify(payload, request=request, form_data=form_data)
    if use_replay:
        result = await sync_to_async(_enforce_replay)(result, v.name)
    await sync_to_async(_emit)(result, verifier=v, request=request, payload=payload)
    return result


@receiver(setting_changed)
def _reset_instances(*, setting: str, **_kwargs: object) -> None:
    if setting.startswith("ALTCHA_") or setting in {"CACHES", "STATIC_URL"}:
        _INSTANCES.clear()
