"""Client-IP resolution behind proxies, and the bundled rate-limit gate."""

from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings

from altcha_django.checks import check_config
from altcha_django.ratelimit import client_ip, simple_ip_ratelimit

pytestmark = pytest.mark.django_db

PROXY = "10.0.0.1"
CLIENT = "203.0.113.7"


def req(xff=None, remote=PROXY):
    extra = {"REMOTE_ADDR": remote}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    return RequestFactory().get("/", **extra)


# --- untrusted by default ----------------------------------------------
def test_no_trusted_proxies_ignores_the_header():
    assert client_ip(req(xff=f"{CLIENT}, {PROXY}")) == PROXY


def test_no_header_returns_remote_addr():
    assert client_ip(req()) == PROXY


def test_missing_remote_addr_is_reported_as_unknown():
    request = RequestFactory().get("/")
    request.META.pop("REMOTE_ADDR", None)
    assert client_ip(request) == "unknown"


# --- with trusted proxies ----------------------------------------------
@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_client_is_taken_from_the_chain_behind_a_trusted_proxy():
    assert client_ip(req(xff=f"{CLIENT}, 10.0.0.5")) == CLIENT


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_spoofed_prefix_cannot_impersonate_another_client():
    """A forged left-hand entry is skipped: the rightmost untrusted hop wins."""
    assert client_ip(req(xff=f"1.1.1.1, 9.9.9.9, {CLIENT}, 10.0.0.5")) == CLIENT


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_header_from_an_untrusted_peer_is_ignored():
    # request arrived directly from the internet, not via our proxy
    assert client_ip(req(xff=f"{CLIENT}", remote="198.51.100.4")) == "198.51.100.4"


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_all_hops_trusted_falls_back_to_the_peer():
    assert client_ip(req(xff="10.0.0.7, 10.0.0.5")) == PROXY


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.1"])
def test_single_address_entry_without_cidr():
    assert client_ip(req(xff=CLIENT)) == CLIENT


@override_settings(ALTCHA_TRUSTED_PROXIES=["2001:db8::/32"])
def test_ipv6_proxies():
    assert client_ip(req(xff=CLIENT, remote="2001:db8::1")) == CLIENT


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_garbage_chain_entries_are_skipped():
    assert client_ip(req(xff=f"not-an-ip, {CLIENT}, 10.0.0.5")) == CLIENT


@override_settings(ALTCHA_TRUSTED_PROXIES=["nonsense/99"])
def test_unparseable_trusted_proxy_fails_closed():
    # never matches -> the header stays untrusted (checks.E012 reports it)
    assert client_ip(req(xff=CLIENT)) == PROXY


def test_explicit_argument_overrides_the_setting():
    assert client_ip(req(xff=CLIENT), trusted_proxies=["10.0.0.0/8"]) == CLIENT


# --- system check -------------------------------------------------------
@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8", "192.168.1.5", "2001:db8::/32"])
def test_e012_not_raised_for_valid_entries():
    assert "altcha.E012" not in {m.id for m in check_config(None)}


@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8", "not-an-ip"])
def test_e012_reports_invalid_entries():
    msg = next(m for m in check_config(None) if m.id == "altcha.E012")
    assert "not-an-ip" in msg.msg
    assert "10.0.0.0/8" not in msg.msg


@override_settings(ALTCHA_TRUSTED_PROXIES="10.0.0.0/8")
def test_e012_rejects_a_bare_string():
    msg = next(m for m in check_config(None) if m.id == "altcha.E012")
    assert "not a string" in msg.msg


# --- the gate itself ----------------------------------------------------
@override_settings(ALTCHA_TRUSTED_PROXIES=["10.0.0.0/8"])
def test_gate_buckets_per_resolved_client():
    gate = simple_ip_ratelimit("1/m")
    assert gate(req(xff=f"{CLIENT}, 10.0.0.5")) is True
    assert gate(req(xff=f"{CLIENT}, 10.0.0.5")) is False
    # a different real client keeps its own bucket
    assert gate(req(xff="203.0.113.99, 10.0.0.5")) is True


def test_forged_header_cannot_mint_fresh_buckets():
    """Without trusted proxies every request from one peer shares a bucket."""
    gate = simple_ip_ratelimit("1/m")
    assert gate(req(xff="1.1.1.1", remote="198.51.100.4")) is True
    assert gate(req(xff="2.2.2.2", remote="198.51.100.4")) is False
