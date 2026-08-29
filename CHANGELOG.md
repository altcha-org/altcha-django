# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - Unreleased

### Added

- First release. Built around the ALTCHA **Widget v3** and **Proof-of-Work v2**.
- `AltchaField` / `AltchaWidget` — a full Django form field: `Form`, `ModelForm`,
  formsets, `Widget.Media` (ES-module `<script>`), translated (`gettext_lazy`)
  error messages keyed by a stable `ErrorCode`, and every widget option as a
  plain keyword argument (no subclassing).
- Local challenges support both PoW v2 difficulty modes, selected by the config
  (as in the `altcha` library): **probabilistic** via `ALTCHA_CHALLENGE["key_prefix"]`
  (default `"00"`; longer = harder), or **deterministic** by setting
  `ALTCHA_CHALLENGE["max_number"]` (random `counter` — bounded, predictable client
  work and a cheap server verify, as in the official `altcha-lib` server example).
- Pluggable verification backend (`ALTCHA_VERIFIER`): `LocalVerifier` (PoW v2),
  `SentinelVerifier` (local server-signature verification or the remote
  `/v1/verify/signature` API), `NullVerifier`, or any dotted path to a
  `BaseVerifier`.
- `run_verification` / `run_averification` — one pipeline used by the field, DRF
  and manual callers: test-mode bypass, atomic replay protection, signals.
- Replay protection via Django's cache framework using an atomic `cache.add`
  claim; TTL derived from the challenge expiry.
- `ChallengeView` (+ async) and an optional same-origin `SentinelChallengeProxyView`.
- Signals: `altcha_verified`, `altcha_verification_failed`, `altcha_replayed`,
  plus an opt-in `CacheStatsRecorder`.
- 15 `django check` system checks (`altcha.E0xx` / `altcha.W0xx`).
- Optional `altcha_django.contrib.rest_framework.AltchaField`.
- Vendored, pinned widget bundle in `static/` (ALTCHA 3.2.2) with a
  `manage.py altcha_vendor_widget` updater; `ALTCHA_WIDGET_JS_SOURCE` switches to
  the jsDelivr CDN or a custom URL.
- Deprecation shims for `django-altcha` setting names
  (`ALTCHA_HMAC_KEY`, `ALTCHA_CHALLENGE_EXPIRE`, `ALTCHA_JS_URL`, …).

### Notes

- Proof-of-Work **v1** payloads are rejected (`code="malformed"`). Configure
  ALTCHA Sentinel to issue v2 challenges.
