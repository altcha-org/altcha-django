"""Exception types raised by altcha-django."""

from __future__ import annotations


class AltchaError(Exception):
    """Base class for all altcha-django errors."""


class AltchaConfigurationError(AltchaError):
    """Raised when altcha-django is misconfigured (bad setting, missing secret, …)."""


class AltchaBackendError(AltchaError):
    """Raised when a verification backend fails in an unexpected, non-user way.

    User-facing verification *failures* are represented as a
    :class:`~altcha_django.results.VerificationResult` with ``verified=False`` and
    never raised; this exception is reserved for programming/transport errors that
    a caller may want to catch explicitly.
    """
