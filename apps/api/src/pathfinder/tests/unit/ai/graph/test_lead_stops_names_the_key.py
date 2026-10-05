"""A turn stopped by a refused key tells the researcher which key to replace."""

from __future__ import annotations

from pydantic import SecretStr

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.lead.sub_agent_tools import UnansweredStage
from pathfinder.domain.provider_keys import KeyRefusal, ProviderKeyring
from pathfinder.platform.errors import (
    DeploymentKeyRefusedError,
    ProviderKeyRefusedError,
)
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests._support.models import ANTHROPIC_SMALL, DEFAULT_MODEL

_KEYRING = ProviderKeyring(active={"anthropic": SecretStr("sk-ant-0123456789WXYZ")})


def _refused_turn() -> _LeadRunCapture:
    capture = _LeadRunCapture()
    capture.lead_model = ANTHROPIC_SMALL
    capture.run_error = str(ProviderKeyRefusedError("Anthropic"))
    return capture


def test_a_turn_that_met_a_refused_key_names_the_key() -> None:
    with attach_keyring(_KEYRING) as keys:
        keys.refusals["anthropic"] = KeyRefusal.INVALID
        reply = final_reply(
            _refused_turn(),
            UnansweredStage(role="frame", model_id=ANTHROPIC_SMALL),
            change="unchanged",
        )

    assert reply is not None
    assert reply.prose == (
        "I stopped this turn: Anthropic refused the key you added, so nothing "
        "more ran on it. Replace or remove your Anthropic key in Settings, "
        "under Provider keys, then send the message again."
    )


def test_a_failure_with_no_refused_key_still_offers_another_model() -> None:
    capture = _refused_turn()
    model_name = ANTHROPIC_SMALL.partition(":")[2]
    capture.run_error = f"status_code: 503, model_name: {model_name}, body: None"

    with attach_keyring(_KEYRING):
        reply = final_reply(capture, None, change="unchanged")

    assert reply is not None
    assert "Choose a different model for that stage" in reply.prose
    assert "Provider keys" not in reply.prose


def test_a_refused_key_after_a_landed_change_asks_for_the_check() -> None:
    with attach_keyring(_KEYRING) as keys:
        keys.refusals["anthropic"] = KeyRefusal.INVALID
        reply = final_reply(_refused_turn(), None, change="unchecked")

    assert reply is not None
    assert "send the message again" not in reply.prose
    assert reply.prose.endswith(
        "then ask me to check the change shown beside this reply, which landed."
    )


def test_a_refused_key_after_a_checked_change_asks_to_go_on() -> None:
    with attach_keyring(_KEYRING) as keys:
        keys.refusals["anthropic"] = KeyRefusal.INVALID
        reply = final_reply(_refused_turn(), None, change="checked")

    assert reply is not None
    assert reply.prose.endswith(
        "then ask me to go on from the change shown beside this reply, which "
        "landed and was checked."
    )


_DEPLOYMENT_REFUSED = (
    "I stopped this turn: OpenAI refused the request on the deployment's "
    "account (no credit remaining). A different model or a resend does not "
    "help until that account is restored. A key of your own, added in Settings "
    "under Provider keys, runs the turn on your account instead."
)


def _deployment_refused_turn() -> _LeadRunCapture:
    capture = _LeadRunCapture()
    capture.lead_model = DEFAULT_MODEL
    capture.run_error = str(DeploymentKeyRefusedError("OpenAI", KeyRefusal.NO_CREDIT))
    return capture


def test_a_refusal_of_the_deployment_key_names_the_account_and_no_model() -> None:
    with attach_keyring(ProviderKeyring()) as keys:
        keys.deployment_refusals["openai"] = KeyRefusal.NO_CREDIT
        reply = final_reply(_deployment_refused_turn(), None, change="unchanged")

    assert reply is not None
    assert reply.prose == _DEPLOYMENT_REFUSED
    assert "http" not in reply.prose


def test_a_refusal_of_the_deployment_key_after_a_landed_change_asks_for_the_check() -> (
    None
):
    with attach_keyring(ProviderKeyring()) as keys:
        keys.deployment_refusals["openai"] = KeyRefusal.NO_CREDIT
        reply = final_reply(_deployment_refused_turn(), None, change="unchecked")

    assert reply is not None
    assert reply.prose == (
        f"{_DEPLOYMENT_REFUSED} The change shown beside this reply landed and was "
        "not checked. Ask me to check it and I will go on from there."
    )


def test_a_refusal_of_the_deployment_key_after_a_checked_change_says_so() -> None:
    with attach_keyring(ProviderKeyring()) as keys:
        keys.deployment_refusals["openai"] = KeyRefusal.NO_CREDIT
        reply = final_reply(_deployment_refused_turn(), None, change="checked")

    assert reply is not None
    assert reply.prose == (
        f"{_DEPLOYMENT_REFUSED} The change shown beside this reply landed and was "
        "checked; what the check found is shown beside it."
    )


def test_a_refused_researcher_key_is_named_before_the_deployment_account() -> None:
    with attach_keyring(_KEYRING) as keys:
        keys.refusals["anthropic"] = KeyRefusal.INVALID
        keys.deployment_refusals["openai"] = KeyRefusal.NO_CREDIT
        reply = final_reply(_refused_turn(), None, change="unchanged")

    assert reply is not None
    assert reply.prose.startswith(
        "I stopped this turn: Anthropic refused the key you added"
    )
