"""Download and vendor the ALTCHA widget bundle into this package's static dir."""

from __future__ import annotations

import hashlib
import urllib.request
from base64 import b64encode
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

_PKG_STATIC = Path(__file__).resolve().parents[2] / "static" / "altcha_django"
_MAIN = "https://cdn.jsdelivr.net/npm/altcha@{version}/dist/main/altcha.min.js"
_I18N = "https://cdn.jsdelivr.net/npm/altcha@{version}/dist/i18n/all.js"


class Command(BaseCommand):
    help = "Vendor altcha.min.js (and optionally the i18n bundle) from jsDelivr."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--altcha-version",
            dest="altcha_version",
            default="3",
            help="npm version or range to fetch (default: 3)",
        )
        parser.add_argument("--i18n", action="store_true", help="also fetch the i18n bundle")

    def handle(self, *args: Any, **options: Any) -> None:
        version = options["altcha_version"]
        _PKG_STATIC.mkdir(parents=True, exist_ok=True)

        main = self._download(_MAIN.format(version=version))
        (_PKG_STATIC / "altcha.min.js").write_bytes(main)
        sri = "sha384-" + b64encode(hashlib.sha384(main).digest()).decode()
        (_PKG_STATIC / "altcha.min.js.SRI").write_text(sri + "\n")
        (_PKG_STATIC / "altcha.min.js.VERSION").write_text(version + "\n")
        self.stdout.write(self.style.SUCCESS(f"Wrote altcha.min.js ({len(main)} bytes)"))
        self.stdout.write(f"  integrity: {sri}")

        if options["i18n"]:
            i18n = self._download(_I18N.format(version=version))
            (_PKG_STATIC / "i18n").mkdir(exist_ok=True)
            (_PKG_STATIC / "i18n" / "all.js").write_bytes(i18n)
            self.stdout.write(self.style.SUCCESS(f"Wrote i18n/all.js ({len(i18n)} bytes)"))

    def _download(self, url: str) -> bytes:
        self.stdout.write(f"Fetching {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - https
                if resp.status != 200:
                    raise CommandError(f"HTTP {resp.status} for {url}")
                return resp.read()
        except OSError as exc:  # pragma: no cover - network
            raise CommandError(f"Download failed: {exc}") from exc
