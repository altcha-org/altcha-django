"""Django integration for ALTCHA — Widget v3, Proof-of-Work v2, and Sentinel."""

from __future__ import annotations

from .challenge import ChallengeConfig, build_challenge, get_challenge_config
from .exceptions import AltchaBackendError, AltchaConfigurationError, AltchaError
from .forms import AltchaField, AltchaMixin, AltchaModelFormMixin
from .results import Classification, ErrorCode, PayloadType, VerificationResult
from .signals import altcha_replayed, altcha_verification_failed, altcha_verified
from .verifiers import (
    BaseVerifier,
    LocalVerifier,
    NullVerifier,
    SentinelVerifier,
    get_verifier,
    register_verifier,
    run_averification,
    run_verification,
)
from .widgets import AltchaWidget

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # forms / widgets
    "AltchaField",
    "AltchaMixin",
    "AltchaModelFormMixin",
    "AltchaWidget",
    # results
    "VerificationResult",
    "PayloadType",
    "Classification",
    "ErrorCode",
    # verifiers
    "BaseVerifier",
    "LocalVerifier",
    "SentinelVerifier",
    "NullVerifier",
    "get_verifier",
    "register_verifier",
    "run_verification",
    "run_averification",
    # challenge
    "build_challenge",
    "get_challenge_config",
    "ChallengeConfig",
    # signals
    "altcha_verified",
    "altcha_verification_failed",
    "altcha_replayed",
    # exceptions
    "AltchaError",
    "AltchaConfigurationError",
    "AltchaBackendError",
]
