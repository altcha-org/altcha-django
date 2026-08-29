# Signals & stats

All three signals fire from `run_verification()` / `run_averification()` — so
forms, DRF and manual callers behave identically. `sender` is the verifier class.

| Signal | When | Extra kwargs |
|---|---|---|
| `altcha_verified` | success | — |
| `altcha_verification_failed` | any failure | `code` (an `ErrorCode` value) |
| `altcha_replayed` | payload reused | `replay_id`; also fires `altcha_verification_failed(code="replayed")` |

Common kwargs: `result` (`VerificationResult`), `verifier`, `request`, `payload`.
An empty submission fires **nothing**.

```python
from django.dispatch import receiver
from altcha_django.signals import altcha_verification_failed

@receiver(altcha_verification_failed)
def log_altcha_failure(sender, result, request, code, **kwargs):
    logger.warning("ALTCHA %s from %s", code, request.META.get("REMOTE_ADDR") if request else "?")
```

## Built-in stats

```python
ALTCHA_COLLECT_STATS = True
```

Connects `CacheStatsRecorder`, which keeps approximate 24h counters in the cache:

```python
from altcha_django.stats import recorder
recorder.snapshot()
# {"ok:total": 1234, "fail:total": 56, "ok:pow_v2": 1234, "fail:invalid_solution": 40, ...}
```

Cache counters are best-effort; for durable analytics connect your own receiver.
