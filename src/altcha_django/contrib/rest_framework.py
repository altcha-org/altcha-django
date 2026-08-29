"""Django REST Framework integration.

Import guarded — this module only works when ``djangorestframework`` is installed
(``pip install 'altcha-django[drf]'``).

::

    from rest_framework import serializers
    from altcha_django.contrib.rest_framework import AltchaField

    class ContactSerializer(serializers.Serializer):
        email = serializers.EmailField()
        altcha = AltchaField(bind_fields=["email"])
"""

from __future__ import annotations

from typing import Any

try:
    from rest_framework import serializers
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "altcha_django.contrib.rest_framework requires djangorestframework. "
        "Install with: pip install 'altcha-django[drf]'"
    ) from exc

from ..forms import AltchaField as _FormField
from ..results import ErrorCode, VerificationResult
from ..verifiers import run_averification, run_verification


class AltchaField(serializers.CharField):
    """Serializer field that verifies an ALTCHA payload.

    ``bind_fields`` lists sibling field names whose *submitted* values are passed
    to the verifier for Sentinel ``fieldsHash`` checks.
    """

    default_error_messages = {
        code: str(msg) for code, msg in _FormField.default_error_messages.items()
    }

    def __init__(
        self,
        *,
        verifier: Any = None,
        replay_protection: bool | None = None,
        test_mode: bool | None = None,
        bind_fields: list[str] | None = None,
        return_result: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("write_only", True)
        kwargs.setdefault("trim_whitespace", False)
        super().__init__(**kwargs)
        self.verifier = verifier
        self.replay_protection = replay_protection
        self.test_mode = test_mode
        self.bind_fields = list(bind_fields or [])
        self.return_result = return_result

    # -- helpers ----------------------------------------------------
    def _request(self) -> Any:
        return (self.context or {}).get("request")

    def _form_data(self) -> dict[str, Any] | None:
        if not self.bind_fields:
            return None
        source = getattr(self.parent, "initial_data", {}) or {}
        return {name: source.get(name, "") for name in self.bind_fields}

    # -- DRF hooks --------------------------------------------------
    def to_internal_value(self, data: Any) -> Any:
        value = super().to_internal_value(data)
        result = run_verification(
            value,
            verifier=self.verifier,
            request=self._request(),
            form_data=self._form_data(),
            replay=self.replay_protection,
            test_mode=self.test_mode,
        )
        self._raise_for(result)
        return result if self.return_result else value

    async def ato_internal_value(self, data: Any) -> Any:
        value = super().to_internal_value(data)
        result = await run_averification(
            value,
            verifier=self.verifier,
            request=self._request(),
            form_data=self._form_data(),
            replay=self.replay_protection,
            test_mode=self.test_mode,
        )
        self._raise_for(result)
        return result if self.return_result else value

    def _raise_for(self, result: VerificationResult) -> None:
        if result.verified:
            return
        code = result.code or ErrorCode.UNVERIFIED.value
        if code not in self.error_messages:
            code = ErrorCode.UNVERIFIED.value
        self.fail(code)
