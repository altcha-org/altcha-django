"""The ``<altcha-widget>`` form widget."""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.forms.utils import flatatt
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.translation import get_language

from .conf import conf

#: Plain HTML attributes understood by the v3 custom element. Everything else must
#: travel inside the ``configuration`` JSON attribute.
ELEMENT_ATTRS = ("auto", "display", "type", "language", "workers", "theme")

#: The remaining v3 attributes, which this widget renders itself from the bound
#: field. Supplying them through ``ALTCHA_WIDGET_DEFAULTS`` would emit a duplicate
#: attribute, so they are filtered out and reported by ``checks.W014``.
WIDGET_MANAGED_ATTRS = ("name", "challenge", "configuration")


class ModuleScript:
    """A ``forms.Media`` JS entry that renders as ``<script type="module">``.

    Implemented as an object with ``__html__`` (rather than a ``Media`` subclass)
    so it survives ``form.media`` composition, which rebuilds a plain ``Media``
    and would otherwise drop a custom subclass.
    """

    def __init__(self, src: str) -> None:
        self.src = str(src)

    def __html__(self) -> str:
        return format_html('<script type="module" src="{}"></script>', self.src)

    def __str__(self) -> str:  # used by Media when no __html__ path is taken
        return self.src

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ModuleScript):
            return self.src == other.src
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("altcha-module-script", self.src))

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"ModuleScript({self.src!r})"


def widget_js_url() -> str:
    source = conf.WIDGET_JS_SOURCE
    if source == "cdn":
        return conf.WIDGET_JS_CDN
    if source == "custom":
        return conf.WIDGET_JS_URL or ""
    return static("altcha_django/altcha.min.js")


def widget_i18n_js_url() -> str | None:
    if not conf.WIDGET_I18N:
        return None
    if conf.WIDGET_I18N_JS_URL:
        return conf.WIDGET_I18N_JS_URL
    if conf.WIDGET_JS_SOURCE == "cdn":
        return conf.WIDGET_I18N_JS_CDN
    return static("altcha_django/i18n/all.js")


class AltchaWidget(forms.Widget):
    """Renders a single ``<altcha-widget>`` element.

    All configuration is passed as constructor kwargs — subclassing is never
    required. ``challenge`` (inline dict/JSON) and ``challenge_url`` are mutually
    exclusive with the verifier-driven default.
    """

    template_name = "altcha_django/widget.html"

    def __init__(
        self,
        *,
        challenge_url: str | None = None,
        challenge: dict | str | None = None,
        challenge_mode: str | None = None,
        configuration: dict | None = None,
        verifier: Any = None,
        test: bool | None = None,
        auto: str | None = None,
        display: str | None = None,
        type: str | None = None,
        language: str | None = None,
        workers: int | None = None,
        theme: str | None = None,
        floating: bool | None = None,
        attrs: dict | None = None,
    ) -> None:
        super().__init__(attrs)
        self.challenge_url = challenge_url
        self.challenge = challenge
        self.challenge_mode = challenge_mode
        self.configuration = dict(configuration or {})
        self.verifier = verifier
        self.test = test
        self.auto = auto
        self.display = "floating" if floating else display
        self.type = type
        self.language = language
        self.workers = workers
        self.theme = theme

    # -- form plumbing ------------------------------------------------
    def value_from_datadict(self, data: Any, files: Any, name: str) -> Any:
        return data.get(name)

    def value_omitted_from_data(self, data: Any, files: Any, name: str) -> bool:
        return name not in data

    def use_required_attribute(self, initial: Any) -> bool:
        return False

    def id_for_label(self, id_: str) -> str:
        return ""

    # -- rendering --------------------------------------------------
    def _resolved_verifier(self) -> Any:
        from .verifiers import resolve_verifier

        return resolve_verifier(self.verifier)

    def _resolve_challenge(self, verifier: Any) -> tuple[str, bool]:
        """Return ``(value, is_inline)`` for the ``challenge`` attribute."""
        if self.challenge is not None:
            if isinstance(self.challenge, str):
                return self.challenge, True
            return json.dumps(self.challenge), True
        if self.challenge_url is not None:
            return str(self.challenge_url), False

        ref = verifier.get_widget_challenge_ref()
        if ref:
            return str(ref), False

        mode = self.challenge_mode or conf.WIDGET_CHALLENGE_MODE
        if mode == "inline":
            return json.dumps(verifier.get_challenge()), True
        try:
            return reverse("altcha_django:challenge"), False
        except NoReverseMatch:
            if mode == "endpoint":
                raise
            return json.dumps(verifier.get_challenge()), True

    def get_context(self, name: str, value: Any, attrs: dict | None) -> dict:
        context = super().get_context(name, value, attrs)
        verifier = self._resolved_verifier()
        src, inline = self._resolve_challenge(verifier)

        test = conf.TEST_MODE if self.test is None else self.test
        configuration = {**conf.WIDGET_CONFIGURATION, **self.configuration}
        # The v3 element has no `test` attribute; test mode travels in the
        # `configuration` JSON.
        if test:
            configuration.setdefault("test", True)

        if getattr(verifier, "spamfilter", False) and "verifyUrl" not in configuration:
            configuration["verifyUrl"] = verifier.widget_verify_url

        # Keys the element cannot read are dropped rather than rendered as inert
        # (or, for `name`, duplicate) attributes; checks.W014 reports them.
        element = {k: v for k, v in conf.WIDGET_DEFAULTS.items() if k in ELEMENT_ATTRS}
        for attr in ELEMENT_ATTRS:
            override = getattr(self, attr, None)
            if override is not None:
                element[attr] = override

        # Ordinary Django ``attrs`` (class, id, data-*, ...) render on the element
        # too. The widget's own options win, and attributes it manages itself are
        # dropped so they can be neither duplicated nor overridden from a template.
        html_attrs = {
            key: val
            for key, val in (context["widget"].get("attrs") or {}).items()
            if key not in WIDGET_MANAGED_ATTRS
        }
        element = {**html_attrs, **element}
        # Only fall back to the active language when nobody asked for one.
        element.setdefault("language", get_language())
        element = {k: v for k, v in element.items() if v is not None and v != ""}

        context["widget"].update(
            widget_name=name,
            challenge_url=None if inline else src,
            challenge_json=None if not inline else src,
            configuration_json=json.dumps(configuration) if configuration else None,
            element=element,
            # flatatt gives HTML-correct booleans (True -> bare, False -> omitted)
            # and escaping, matching how every other Django widget renders attrs.
            element_attrs=flatatt(element),
        )
        return context

    @property
    def media(self) -> forms.Media:
        js: list[Any] = [ModuleScript(widget_js_url())]
        i18n = widget_i18n_js_url()
        if i18n:
            js.append(ModuleScript(i18n))
        return forms.Media(js=js)
