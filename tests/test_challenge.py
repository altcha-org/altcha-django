from __future__ import annotations

import base64
import json

import pytest
from altcha import verify_solution
from django.test import override_settings

from altcha_django.challenge import ChallengeConfig, build_challenge, get_challenge_config
from altcha_django.exceptions import AltchaConfigurationError

pytestmark = pytest.mark.django_db


def test_build_challenge_is_signed_and_verifiable():
    challenge = build_challenge(hmac_secret="s3cret")
    data = challenge.to_dict()
    assert data["signature"]
    assert data["parameters"]["algorithm"] == "PBKDF2/SHA-256"
    # round-trip: solve then verify with the same secret
    from altcha import Payload, solve_challenge

    payload = Payload(challenge, solve_challenge(challenge)).to_base64()
    assert verify_solution(payload, "s3cret").verified is True


def test_deterministic_mode_when_max_number_set():
    from altcha import Payload, solve_challenge

    challenge = build_challenge(hmac_secret="s", config=ChallengeConfig(cost=20, max_number=40))
    params = challenge.to_dict()["parameters"]
    assert params["keyPrefix"] != "00"  # real derived-key prefix is embedded
    solution = solve_challenge(challenge)
    assert 20 <= solution.counter < 40  # [max_number // 2, max_number)
    assert verify_solution(Payload(challenge, solution).to_base64(), "s").verified


def test_probabilistic_mode_when_max_number_unset():
    from altcha import Payload, solve_challenge

    challenge = build_challenge(
        hmac_secret="s", config=ChallengeConfig(cost=20, max_number=None, key_prefix="0")
    )
    assert challenge.to_dict()["parameters"]["keyPrefix"] == "0"
    payload = Payload(challenge, solve_challenge(challenge)).to_base64()
    assert verify_solution(payload, "s").verified


def test_non_hex_key_prefix_rejected():
    with pytest.raises(AltchaConfigurationError):
        ChallengeConfig(key_prefix="zz").validate()


def test_explicit_counter_override_forces_deterministic():
    from altcha import solve_challenge

    challenge = build_challenge(
        hmac_secret="s", counter=7, config=ChallengeConfig(cost=20, max_number=None)
    )
    assert solve_challenge(challenge).counter == 7


def test_build_challenge_requires_a_secret():
    with override_settings(ALTCHA_HMAC_SECRET=None):
        with pytest.raises(AltchaConfigurationError):
            build_challenge()


def test_challenge_embeds_expiry():
    challenge = build_challenge(
        hmac_secret="s", config=ChallengeConfig(cost=50, expires_seconds=120)
    )
    assert challenge.to_dict()["parameters"]["expiresAt"] > 0


def test_bind_session_token_added_to_data():
    challenge = build_challenge(hmac_secret="s", bind_session_token=True)
    assert "id" in challenge.to_dict()["parameters"]["data"]


def test_unknown_challenge_key_rejected():
    with override_settings(ALTCHA_CHALLENGE={"nonsense": 1}):
        with pytest.raises(AltchaConfigurationError):
            get_challenge_config()


def test_unknown_algorithm_rejected():
    with pytest.raises(AltchaConfigurationError):
        get_challenge_config(algorithm="ROT13")


@override_settings(  # legacy milliseconds setting, with no explicit expires_seconds
    ALTCHA_CHALLENGE_EXPIRE=300_000,
    ALTCHA_CHALLENGE={"algorithm": "PBKDF2/SHA-256", "cost": 200},
)
def test_legacy_challenge_expire_ms_is_honoured():
    cfg = get_challenge_config()
    assert cfg.expires_seconds == 300


def test_challenge_to_dict_matches_widget_shape():
    data = build_challenge(hmac_secret="s").to_dict()
    assert set(data) == {"parameters", "signature"}
    assert {"algorithm", "cost", "nonce", "salt"} <= set(data["parameters"])
    # serialisable
    json.loads(json.dumps(data))
    # base64 round trip like the widget would submit
    base64.b64encode(json.dumps(data).encode())


# --- memory_cost ---------------------------------------------------------
def test_memory_cost_reaches_the_challenge_parameters():
    # explicit config -> max_number stays None -> probabilistic, so no server-side KDF
    cfg = ChallengeConfig(algorithm="SCRYPT", cost=2, memory_cost=8, parallelism=1)
    challenge = build_challenge(hmac_secret="s3cret", config=cfg)
    assert challenge.parameters.memory_cost == 8
    assert challenge.to_dict()["parameters"]["memoryCost"] == 8


def test_config_exposes_memory_cost_field():
    cfg = get_challenge_config(memory_cost=4096)
    assert cfg.memory_cost == 4096
    assert not hasattr(cfg, "max_memory")


@override_settings(ALTCHA_CHALLENGE={"max_memory": 4096})
def test_max_memory_is_not_a_valid_key():
    """The parameter is `memory_cost`, as in the altcha library and the widget."""
    with pytest.raises(AltchaConfigurationError, match="max_memory"):
        get_challenge_config()
