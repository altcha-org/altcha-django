# altcha-django demo project

A minimal Django project showing `altcha-django` with a contact form, a formset,
a DRF endpoint, and a stats page.

## Run it

From the **repository root**:

```console
python -m venv .venv && source .venv/bin/activate      # or: uv venv && source .venv/bin/activate
pip install -e ".[dev]"                                 # installs Django, DRF, altcha-django

cd example
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

| URL | What |
|---|---|
| `/` | contact form (`ContactForm`) |
| `/formset/` | the same form in a formset |
| `/api/contact/` | DRF endpoint (`POST` JSON) |
| `/stats/` | `CacheStatsRecorder.snapshot()` as JSON |
| `/altcha/challenge/` | the bundled challenge endpoint |

## Local vs Sentinel

Default is **local** proof-of-work (a throwaway `ALTCHA_HMAC_SECRET`).

To exercise **Sentinel**, point it at your self-hosted instance:

```console
export ALTCHA_DEMO_MODE=sentinel
export ALTCHA_SENTINEL_CHALLENGE_URL="https://sentinel.example.com/v1/challenge?apiKey=key_..."
export ALTCHA_SENTINEL_API_SECRET="sec_..."
python manage.py runserver
```
