"""A turn stopped by a refused key tells the researcher which key to replace."""

from __future__ import annotations

from pydantic import SecretStr

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.lead.sub_agent_tools import UnansweredStage
from pathfinder.domain.provider_keys import KeyRefusal, ProviderKeyring
from pathfinder.platform.errors import ProviderKeyRefusedError
from pathfinder.platform.model_keys import attach_keyring

_KEYRING = ProviderKeyring(active={"anthropic": SecretStr("sk-ant-0123456789WXYZ")})


def _refused_turn() -> _LeadRunCapture:
    capture = _LeadRunCapture()
    capture.lead_model = "anthropic:claude-opus-5"
    capture.run_error = str(ProviderKeyRefusedError("Anthropic"))
    return capture


def test_a_turn_that_met_a_refused_key_names_the_key() -> None:
    with attach_keyring(_KEYRING) as keys:
        keys.refusals["anthropic"] = KeyRefusal.INVALID
        reply = final_reply(
            _refused_turn(),
            UnansweredStage(role="frame", model_id="anthropic:claude-opus-5"),
            changed=False,
        )

    assert reply is not None
    assert reply.prose == (
        "I stopped this turn: Anthropic refused the key you added, so nothing "
        "more ran on it. Replace or remove your Anthropic key in Settings, "
        "under Provider keys, then send the message again."
    )


def test_a_failure_with_no_refused_key_still_offers_another_model() -> None:
    capture = _refused_turn()
    capture.run_error = "status_code: 503, model_name: claude-opus-5, body: None"

    with attach_keyring(_KEYRING):
        reply = final_reply(capture, None, changed=False)

    assert reply is not None
    assert "Choose a different model for that stage" in reply.prose
    assert "Provider keys" not in reply.prose
