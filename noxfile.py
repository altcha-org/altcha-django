"""Test / lint / packaging sessions for altcha-django."""

from __future__ import annotations

import nox

nox.options.default_venv_backend = "uv|virtualenv"
nox.options.reuse_existing_virtualenvs = True

#: Django version -> the Pythons it supports, per each release's own
#: "Programming Language :: Python" classifiers on PyPI. Combinations outside
#: this table are skipped rather than failed.
DJANGO_PYTHONS = {
    "4.2": {"3.10", "3.11", "3.12"},
    "5.0": {"3.10", "3.11", "3.12"},
    "5.1": {"3.10", "3.11", "3.12", "3.13"},
    "5.2": {"3.10", "3.11", "3.12", "3.13", "3.14"},
    "6.0": {"3.12", "3.13", "3.14"},
    "6.1": {"3.12", "3.13", "3.14"},
}

PYTHONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
DJANGOS = list(DJANGO_PYTHONS)


@nox.session(python=PYTHONS)
@nox.parametrize("django", DJANGOS)
def tests(session: nox.Session, django: str) -> None:
    if session.python not in DJANGO_PYTHONS[django]:
        session.skip(f"Django {django} does not support Python {session.python}")
    session.install(f"django~={django}.0", "-e", ".[dev]")
    session.run("pytest", "-q", *session.posargs)


@nox.session(python="3.12")
def coverage(session: nox.Session) -> None:
    session.install("django>=5.2", "-e", ".[dev]")
    session.run("pytest", "-q", "--cov=altcha_django", "--cov-report=term-missing", "--cov-fail-under=95")


@nox.session(python="3.12")
def lint(session: nox.Session) -> None:
    session.install("ruff>=0.6")
    session.run("ruff", "check", "src", "tests")
    session.run("ruff", "format", "--check", "src", "tests")


@nox.session(python="3.12")
def types(session: nox.Session) -> None:
    session.install("django>=5.2", "mypy>=1.11", "django-stubs>=5", "-e", ".[dev]")
    session.run("mypy", "src")


@nox.session(python="3.12")
def docs(session: nox.Session) -> None:
    session.install("-e", ".[docs]")
    session.run("mkdocs", "build", "--strict", *session.posargs)


@nox.session(python="3.12")
def pkg(session: nox.Session) -> None:
    session.install("build", "twine", "check-wheel-contents")
    session.run("python", "-m", "build")
    session.run("twine", "check", "dist/*")
    session.run("check-wheel-contents", "dist")
