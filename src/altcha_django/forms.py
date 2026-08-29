"""``AltchaField`` and the form mixins that give it request / sibling-field context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    _MixinBase = forms.BaseForm
else:
    _MixinBase = object

from .results import ErrorCode, VerificationResult
from .verifiers import run_verification
from .widgets import AltchaWidget

_WIDGET_KWARGS = (
    "challenge_url",
    "challenge",
    "challenge_mode",
    "configuration",
    "auto",
    "display",
    "type",
    "language",
    "workers",
    "theme",
    "floating",
)


class AltchaField(forms.Field):
    """A form field that validates an ALTCHA payload.

    Behaves like any other Django field: works in ``Form``, ``ModelForm``,
    formsets, supports ``Widget.Media`` and translated errors. Every widget option
    is a plain keyword argument.

    For request-aware backends (Sentinel ``fieldsHash``, IP checks) add
    :class:`AltchaMixin` to the form and pass ``request=`` when instantiating it.
    """

    widget = AltchaWidget

    default_error_messages = {
        ErrorCode.REQUIRED.value: _("Please complete the ALTCHA verification."),
        ErrorCode.MALFORMED.value: _(
            "The ALTCHA response was invalid. Please reload the page and try again."
        ),
        ErrorCode.INVALID_SIGNATURE.value: _(
            "The ALTCHA challenge could not be validated. Please try again."
        ),
        ErrorCode.INVALID_SOLUTION.value: _(
            "The ALTCHA challenge was not solved correctly. Please try again."
        ),
        ErrorCode.EXPIRED.value: _("The ALTCHA challenge expired. Please try again."),
        ErrorCode.REPLAYED.value: _("This ALTCHA challenge was already used. Please try again."),
        ErrorCode.UNVERIFIED.value: _("Verification failed. Please try again."),
        ErrorCode.CLASSIFICATION_REJECTED.value: _(
            "Your submission looks automated and was blocked."
        ),
        ErrorCode.SCORE_REJECTED.value: _(
            "Your submission could not be verified. Please try again."
        ),
        ErrorCode.FIELDS_HASH_MISMATCH.value: _(
            "The form changed after verification. Please resubmit."
        ),
        ErrorCode.BACKEND_ERROR.value: _(
            "The verification service is unavailable. Please try again shortly."
        ),
        ErrorCode.MISCONFIGURED.value: _("ALTCHA is not configured correctly on this site."),
    }

    def __init__(
        self,
        *,
        verifier: Any = None,
        replay_protection: bool | None = None,
        test_mode: bool | None = None,
        bind_form_fields: list[str] | None = None,
        return_result: bool = False,
        widget_test: bool | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("label", "")
        widget_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _WIDGET_KWARGS}

        super().__init__(**kwargs)

        if not isinstance(self.widget, AltchaWidget):
            self.widget = AltchaWidget()  # type: ignore[assignment]
        self.widget.verifier = verifier
        if widget_test is not None:
            self.widget.test = widget_test
        if widget_kwargs.pop("floating", None):
            widget_kwargs.setdefault("display", "floating")
        for key, value in widget_kwargs.items():
            setattr(self.widget, key, value)

        self.verifier = verifier
        self.replay_protection = replay_protection
        self.test_mode = test_mode
        self.bind_form_fields = list(bind_form_fields or [])
        self.return_result = return_result
        self._request: Any = None
        self._form: forms.BaseForm | None = None

    # -- context injected by AltchaMixin --------------------------------
    def bind_context(self, *, request: Any = None, form: forms.BaseForm | None = None) -> None:
        self._request = request
        self._form = form

    def _collect_form_data(self) -> dict[str, Any] | None:
        if not self.bind_form_fields or self._form is None:
            return None
        data = getattr(self._form, "data", None)
        if data is None:
            return None
        add_prefix = getattr(self._form, "add_prefix", lambda n: n)
        return {name: data.get(add_prefix(name), "") for name in self.bind_form_fields}

    # -- validation --------------------------------------------------
    def to_python(self, value: Any) -> str:
        if value in self.empty_values:
            return ""
        return str(value)

    def validate(self, value: Any) -> None:
        # Only enforce presence here; the real work happens in clean().
        if value in self.empty_values and self.required:
            raise ValidationError(
                self.error_messages[ErrorCode.REQUIRED.value], code=ErrorCode.REQUIRED.value
            )

    def clean(self, value: Any) -> Any:
        value = self.to_python(value)
        self.validate(value)
        if not value:
            return value

        result: VerificationResult = run_verification(
            value,
            verifier=self.verifier,
            request=self._request,
            form_data=self._collect_form_data(),
            replay=self.replay_protection,
            test_mode=self.test_mode,
        )
        if not result.verified:
            code = result.code or ErrorCode.UNVERIFIED.value
            message = self.error_messages.get(
                code, self.error_messages[ErrorCode.UNVERIFIED.value]
            )
            raise ValidationError(message, code=code)

        return result if self.return_result else value


class AltchaMixin(_MixinBase):
    """Mix into a ``Form`` / ``ModelForm`` to give every :class:`AltchaField` the
    current request and access to sibling field values.

    ::

        class ContactForm(AltchaMixin, forms.Form):
            captcha = AltchaField()

        form = ContactForm(request.POST or None, request=request)
    """

    def __init__(self, *args: Any, request: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.altcha_request = request
        for field in self.fields.values():
            if isinstance(field, AltchaField):
                field.bind_context(request=request, form=self)


class AltchaModelFormMixin(AltchaMixin):
    """Alias of :class:`AltchaMixin` for use with ``ModelForm`` (clearer intent)."""
