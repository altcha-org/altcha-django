# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-10-05

### Breaking changes

Despite the minor version, upgrading from 1.0.0 can break deployments and code.
Run `manage.py check --deploy` after upgrading. Details are in the sections below.

- `ALTCHA_SENTINEL_MIN_SCORE` and `SentinelVerifier(min_score=...)` are removed.
  `manage.py check` fails with `altcha.E015` while the setting, or `"min_score"` in
  `ALTCHA_VERIFIER_OPTIONS`, is present (even as `None`), and `SentinelVerifier`
  raises `AltchaConfigurationError` when given `min_score`. The replacement,
  `ALTCHA_SENTINEL_MAX_SCORE` / `max_score=`, has the opposite meaning: do not
  copy the old value.
- `manage.py check` has new errors that can fail a deploy that passed on 1.0.0:
  `altcha.E013` (invalid `ALTCHA_CHALLENGE` values or unknown keys), `altcha.E014`
  (`DummyCache` with replay protection on, previously warning `altcha.W002`, which
  is removed) and `altcha.E015`. `altcha.E010` also rejects an empty or overlong
  `key_prefix`. Issuing a challenge with such settings raises
  `AltchaConfigurationError`.
- Requires `altcha>=2.3.0` (was `>=2.1.0`).
- `ALTCHA_SENTINEL_VERIFY_FIELDS` defaults to `False`. Set it to `True` to keep
  Sentinel field binding on.
- Custom verifiers must set `VerificationResult.replay_id` on success while replay
  protection is on. Otherwise the result fails as `malformed`.
- Custom verifiers receive `form_data` as an `altcha_django.BoundFormData`, a
  read-only mapping keyed by the prefixed HTML field name, instead of a `dict`
  keyed by the unprefixed field name.
- `LocalVerifier.check_session_binding(request, replay_id)` is now
  `check_session_binding(request, token)`. Callers that pass it by keyword must
  rename it.
- Error codes: a Sentinel payload with an unknown hash `algorithm` fails with
  `invalid_signature` (was `malformed`). Payloads that verify but carry no signed
  id now fail as `malformed` instead of being accepted.
- The local replay key is the challenge `nonce` (was `parameters.data.id` when
  present). During the upgrade, a payload accepted under its old key can be
  accepted once more until it expires.

### Security

- `ALTCHA_CHALLENGE` settings that allow solving a challenge without proof of work
  are rejected when a challenge is issued and by `manage.py check`: an empty
  `key_prefix`, a `key_length` below 16 bytes (deterministic mode published an
  empty or near-complete prefix), and a `key_length` above the digest size for
  `SHA-256`/`SHA-384`/`SHA-512` (deterministic mode published the whole derived
  key, which verified with no work when `ALTCHA_CHALLENGE_HMAC_KEY_SECRET` is set).
- Requires `altcha>=2.3.0` (was `>=2.1.0`). Older releases raised on malformed
  solutions (non-hex or odd-length `derivedKey`, out-of-range `counter`, non-string
  `signature`), so any client could turn a form submission into an HTTP 500. These
  payloads now fail validation with `invalid_solution` / `invalid_signature`.
  `altcha.E001` reports installed versions below 2.3.0.
- The local verifier verifies the payload before reading `challenge.parameters`.
  Previously a payload whose `parameters`, `data` or `expiresAt` had an unexpected
  type (e.g. `expiresAt: "abc"`) raised out of `form.is_valid()` as an HTTP 500;
  it now fails validation as `malformed`. Failed results no longer carry a
  `replay_id` / `expires_at` taken from unsigned input.
- Replay protection fails closed: a payload that verifies but carries no signed
  id (e.g. Sentinel `verificationData` without `id`, or a remote verify response
  without one) is rejected as `malformed` instead of being accepted on every
  submission.
- Sentinel field binding (`bind_form_fields` / DRF `bind_fields`) is enforced even
  when the payload has no `fieldsHash`: every bound field submitted with a
  non-empty value must appear in the signed `fields` and match the hash.
  Previously a client could skip classification (send no fields to Sentinel)
  and post arbitrary content in bound fields.
- The Sentinel score threshold was inverted: `ALTCHA_SENTINEL_MIN_SCORE` rejected
  scores *below* the limit, but Sentinel's score rises with spam likelihood, so
  it rejected clean submissions and accepted spam. Replaced by
  `ALTCHA_SENTINEL_MAX_SCORE` / `SentinelVerifier(max_score=...)` (see Changed).

### Changed

- `ALTCHA_CHALLENGE` numbers (`cost`, `key_length`, `expires_seconds`, `max_number`,
  `memory_cost`, `parallelism`) must be positive integers; a `key_prefix` longer than
  the derived key is rejected as unsolvable. `ChallengeConfig.validate()` reports every
  problem at once.
- New checks: `altcha.E013` (invalid `ALTCHA_CHALLENGE` values, including unknown
  keys) and `altcha.W016` (`max_number` below 1000). `altcha.E010` also covers an
  empty or overlong `key_prefix`.
- A Sentinel payload naming an unknown hash `algorithm` now fails with
  `invalid_signature` (previously `malformed`), as reported by `altcha` 2.3.0.
- Custom verifiers must set `VerificationResult.replay_id` on success while
  `ALTCHA_REPLAY_PROTECTION` is on; results without one fail as `malformed`.
  Results with `payload_type=PayloadType.TEST` (test mode, the `null` verifier)
  are exempt.
- `ALTCHA_SENTINEL_VERIFY_FIELDS` defaults to `False`: Sentinel's default setup
  classifies no fields, so field binding is opt-in. When enabled, forms that bind
  fields require Sentinel's spam filter (`ALTCHA_SENTINEL_SPAMFILTER = True`, or a
  widget `verifyUrl`) and bound fields the widget classifies (text inputs and
  textareas); a bound `EmailField` or a disabled spam filter fails every non-empty
  submission with `fields_hash_mismatch`, and `altcha.W012` notes the spam-filter
  case. Docs examples bind a text field instead of an `EmailField`.
- `LocalVerifier.check_session_binding(request, token)`: the second parameter was
  renamed from `replay_id`, since the session token (`data.id`) is no longer the
  replay id.
- `DummyCache` behind `ALTCHA_CACHE_ALIAS` while replay protection is on is now an
  error, `altcha.E014` (was warning `altcha.W002`, now removed): it silently
  disabled replay protection. Set `ALTCHA_REPLAY_PROTECTION = False` to opt out
  explicitly. New warning `altcha.W017` for `FileBasedCache`, whose non-atomic
  `add()` lets concurrent replays both pass. Cache backend detection uses
  `isinstance`, so subclasses are covered. `docs/settings.md` describes which
  backends are suitable and how to configure a dedicated replay cache.
- `ALTCHA_SENTINEL_MIN_SCORE` and `SentinelVerifier(min_score=...)` are removed
  in favour of `ALTCHA_SENTINEL_MAX_SCORE` / `max_score=`, which reject scores
  above the limit. A score that is not a finite number (`"nan"`, `"inf"`, text)
  is rejected as `score_rejected` when a limit is set; exponent and negative
  forms (`1e-7`, `-1`) are parsed instead of raising `TypeError`.
  `VerificationResult.score` is always a `float` or `None`. New error
  `altcha.E015` fails `manage.py check` while `ALTCHA_SENTINEL_MIN_SCORE` is
  still set, so the removed setting is not silently ignored; do not copy its
  value to `ALTCHA_SENTINEL_MAX_SCORE`, the meaning is inverted.
- The vendored widget bundle (`static/altcha_django/altcha.min.js` and
  `i18n/all.js`) is updated from ALTCHA 3.2.2 to 3.3.0. 3.2.2 derived keys
  differently from the server for some accepted `ALTCHA_CHALLENGE` settings, so
  honest users could never verify: `SHA-384`/`SHA-512` with `cost > 1` and `SHA-*`
  with a `key_length` below the digest size (truncated every round instead of
  once), and `PBKDF2/*` with a `key_length` other than 16, 24 or 32 (widget error).
  The example project now binds the `message` text field instead of `email`.
- New warning `altcha.W018`: session binding (`ALTCHA_CHALLENGE_BIND_SESSION`)
  with replay protection off. Binding is not a replay control — consuming the
  session token is not atomic, and signed-cookie sessions can be resent — so a
  solved challenge can be reused unless `ALTCHA_REPLAY_PROTECTION` is on. The
  session-binding docs describe this and the token loss when several challenges
  are fetched for one session at once.

### Fixed

- A per-verifier challenge override set to `None` (e.g.
  `LocalVerifier(challenge={"max_number": None})`) replaces the
  `ALTCHA_CHALLENGE` value instead of being ignored, so a verifier can select
  probabilistic mode, or unset `memory_cost`/`parallelism`, when the settings
  define them.
- The Sentinel replay id is the signed `id` read verbatim from the raw
  `verificationData` (first value, like `URLSearchParams.get`). It was taken from
  the type-coerced parse, so distinct ids such as `0123` / `123`, `1.10` / `1.1`
  or `" abc "` / `abc` shared one replay key, and `0` was treated as missing. In
  remote mode the id now comes from the submitted payload Sentinel verified, not
  from the response body.
- A Sentinel payload signed without `expire` (API key with no expiry) is
  accepted only until `ALTCHA_REPLAY_FALLBACK_TTL` seconds after its signed
  `time`, and its replay entry is kept for that whole window. Previously it never
  expired while its replay entry lapsed after `REPLAY_FALLBACK_TTL`, so it could
  be reused every hour. A payload with neither `expire` nor `time` fails as
  `malformed`.
- The local verifier's replay id is always the signed challenge `nonce`. It was
  `parameters.data.id` when present, so challenges sharing an integrator-supplied
  `data.id` (e.g. `VERIFIER_OPTIONS={"challenge": {"data": {"id": ...}}}`) were
  rejected as `replayed` after the first. `data.id` remains the session-binding
  token. When upgrading, a payload already accepted under its old `data.id` key can
  be accepted once more until it expires (`expires_seconds`, default 600 s), unless
  session binding consumed its token.
- Sentinel `fieldsHash` is always checked as SHA-256, as Sentinel computes it.
  The digest was taken from the payload's `algorithm`, so payloads signed with
  `SHA-1` or `SHA-512` (v1 challenges) failed field binding with
  `fields_hash_mismatch` for honest submissions.
- Sentinel field binding works with form prefixes and with text inputs the widget
  hashed but that are not bound. Bound fields are matched by their prefixed HTML
  name, and the hash is checked against every submitted value Sentinel classified;
  both cases failed honest submissions with `fields_hash_mismatch`. Forms and the
  DRF field pass the new `altcha_django.BoundFormData` as `form_data` (a mapping of
  the bound fields plus `.value(name)` for any submitted field).
- Sentinel remote mode returns `backend_error` for a malformed verify response
  (non-JSON body such as a proxy error page, a JSON value that is not an object,
  or a non-object `verificationData`) instead of raising out of `form.is_valid()`
  as an HTTP 500. A non-string `reason`/`error` no longer crashes the result
  mapping.
- Sentinel field binding reads the signed `fields` and `fieldsHash` verbatim from
  the payload's `verificationData`. A single field name that looks like a value
  (`fields=123`, `true`, `1.5`) was parsed as a number or boolean and raised
  `TypeError` out of `form.is_valid()` (HTTP 500); any client could get Sentinel
  to sign such a name. In remote mode the fields now come from the submitted
  payload Sentinel verified rather than from its re-typed response.
- `manage.py check` reports a malformed `ALTCHA_CHALLENGE` instead of crashing
  with `TypeError`/`AttributeError`: an unhashable `algorithm` (list, dict) is
  `altcha.E009`, and non-string keys or a setting that is not a dict are
  `altcha.E013`. Issuing a challenge with such settings raises
  `AltchaConfigurationError`.

## [1.0.0] - 2026-08-29

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
