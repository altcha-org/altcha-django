"""Signals fired by the verification pipeline.

All three are sent from :func:`altcha_django.verifiers.run_verification` (and its
async twin), so DRF, forms and manual callers behave identically.

Receiver signature::

    def on_altcha(sender, *, result, verifier, request, payload, **kwargs):
        # sender:   the BaseVerifier subclass that produced the result
        # result:   altcha_django.results.VerificationResult
        # verifier: the BaseVerifier instance
        # request:  HttpRequest | None
        # payload:  the raw base64 payload string
        ...

``altcha_verification_failed`` additionally receives ``code`` (an ErrorCode value).
``altcha_replayed`` additionally receives ``replay_id`` and is *also* accompanied
by an ``altcha_verification_failed`` with ``code="replayed"``.

An empty submission (user left the widget unsolved) raises the form's ``required``
error and fires no signal.
"""

from __future__ import annotations

from django.dispatch import Signal

altcha_verified = Signal()
altcha_verification_failed = Signal()
altcha_replayed = Signal()
