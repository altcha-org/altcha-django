#!/usr/bin/env python
"""Convenience entry point: ``python -m tests.runtests [pytest args]``.

Delegates to pytest (the single source of truth for the suite) so it works the
same whether or not pytest is on the PATH.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    try:
        import pytest
    except ImportError:  # pragma: no cover
        sys.stderr.write(
            "pytest is required to run the test suite: pip install 'altcha-django[dev]'\n"
        )
        return 1
    args = sys.argv[1:] or ["tests"]
    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(main())
