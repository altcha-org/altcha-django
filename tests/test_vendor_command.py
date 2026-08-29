from __future__ import annotations

import io

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_vendor_widget_writes_files(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(url, timeout=0):
        calls.append(url)
        body = b"i18n-bundle" if "i18n" in url else b"// altcha bundle"
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "altcha_django.management.commands.altcha_vendor_widget._PKG_STATIC",
        tmp_path,
    )

    out = io.StringIO()
    call_command("altcha_vendor_widget", "--altcha-version", "3.2.2", "--i18n", stdout=out)

    assert (tmp_path / "altcha.min.js").read_bytes() == b"// altcha bundle"
    assert (tmp_path / "altcha.min.js.VERSION").read_text().strip() == "3.2.2"
    assert (tmp_path / "altcha.min.js.SRI").read_text().startswith("sha384-")
    assert (tmp_path / "i18n" / "all.js").read_bytes() == b"i18n-bundle"
    assert any("altcha@3.2.2" in u for u in calls)
    assert "integrity: sha384-" in out.getvalue()


def test_vendor_widget_http_error(monkeypatch, tmp_path):
    from django.core.management.base import CommandError

    class _Err(_FakeResponse):
        status = 500

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=0: _Err(b""))
    monkeypatch.setattr(
        "altcha_django.management.commands.altcha_vendor_widget._PKG_STATIC", tmp_path
    )
    with pytest.raises(CommandError):
        call_command("altcha_vendor_widget")
