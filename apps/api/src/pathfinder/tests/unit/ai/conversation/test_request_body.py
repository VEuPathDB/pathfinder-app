"""``ChatRequestBody`` is the body PROTOCOL.md states, and it accepts only model
ids the catalog defines."""

from __future__ import annotations

import json
import re
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.models.catalog import get_model_catalog
from pathfinder.tests.protocol_document import protocol_section

_CATALOG_MODEL_ID = get_model_catalog()[0].id
_TABLE_KEY = re.compile(r"^\| `([A-Za-z][A-Za-z0-9]*)` \|", re.MULTILINE)
_EXAMPLE = re.compile(r"#### `([^`]+)`\n\n```json\n(.*?)\n```", re.DOTALL)


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "conversationId": str(uuid4()),
        "siteId": "plasmodb",
        "messages": [],
    }
    payload.update(overrides)
    return payload


def test_catalog_model_is_accepted() -> None:
    body = ChatRequestBody.model_validate(
        _body(phaseModels={"lead": _CATALOG_MODEL_ID})
    )

    assert body.phase_models == {"lead": _CATALOG_MODEL_ID}


def test_empty_phase_models_is_accepted() -> None:
    body = ChatRequestBody.model_validate(_body())

    assert body.phase_models == {}


def test_unknown_model_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ChatRequestBody.model_validate(
            _body(phaseModels={"lead": "openai:not-a-real-model"})
        )

    message = str(excinfo.value)
    assert "lead" in message
    assert "openai:not-a-real-model" in message


def test_unknown_model_is_rejected_among_valid_ones() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ChatRequestBody.model_validate(
            _body(
                phaseModels={
                    "lead": _CATALOG_MODEL_ID,
                    "verification": "anthropic:claude-does-not-exist",
                }
            )
        )

    message = str(excinfo.value)
    assert "verification" in message
    assert "anthropic:claude-does-not-exist" in message


def test_reasoning_effort_outside_the_literal_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequestBody.model_validate(_body(phaseReasoning={"lead": "extreme"}))


def test_a_rehydrated_assistant_message_with_turn_facts_is_accepted() -> None:
    """The protocol's reduction adds errors/aborted/finishReason; the request
    reads the thread as the client holds it, so those members parse away."""
    body = ChatRequestBody.model_validate(
        _body(
            messages=[
                {
                    "id": "m1",
                    "role": "assistant",
                    "parts": [{"type": "text", "text": "done"}],
                    "errors": [],
                    "aborted": False,
                    "finishReason": "stop",
                },
                {
                    "id": "m2",
                    "role": "user",
                    "parts": [{"type": "text", "text": "next question"}],
                },
            ]
        )
    )

    assert len(body.messages) == 2
    assert body.messages[0].role == "assistant"


def test_a_tool_part_carrying_its_own_summary_is_accepted() -> None:
    """A conforming reducer folds `data-tool-summary` onto the call's part; the
    strict part union forbids the two fields on resend, so they parse away."""
    body = ChatRequestBody.model_validate(
        _body(
            messages=[
                {
                    "id": "m1",
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool-search_eda_studies",
                            "toolCallId": "c1",
                            "state": "output-available",
                            "input": {},
                            "output": {"studies": 3},
                            "summary": "3 studies matched heat shock",
                            "summaryStatus": "ok",
                        }
                    ],
                },
                {
                    "id": "m2",
                    "role": "user",
                    "parts": [{"type": "text", "text": "open the first one"}],
                },
            ]
        )
    )

    assert len(body.messages) == 2


def test_an_oversized_site_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        ChatRequestBody.model_validate(_body(siteId="s" * 51))


def test_a_failed_tool_part_with_provider_metadata_is_accepted() -> None:
    """A live stream records resultProviderMetadata on an output-error part;
    the strict part union forbids it on resend, so it parses away."""
    body = ChatRequestBody.model_validate(
        _body(
            messages=[
                {
                    "id": "m1",
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool-classify_user_intent",
                            "toolCallId": "c1",
                            "state": "output-error",
                            "errorText": "differential_sides caps at 2",
                            "input": {},
                            "resultProviderMetadata": {"openai": {"x": 1}},
                        }
                    ],
                },
                {
                    "id": "m2",
                    "role": "user",
                    "parts": [{"type": "text", "text": "use the first two"}],
                },
            ]
        )
    )

    assert len(body.messages) == 2


def _documented_examples() -> dict[str, str]:
    return dict(_EXAMPLE.findall(protocol_section("request_examples")))


def _model_field_names() -> set[str]:
    return {field.alias or name for name, field in ChatRequestBody.model_fields.items()}


def test_the_two_field_tables_name_every_field_the_body_accepts() -> None:
    documented = set(_TABLE_KEY.findall(protocol_section("request_core"))) | set(
        _TABLE_KEY.findall(protocol_section("request_extensions")),
    )

    assert documented == _model_field_names()


def test_no_field_is_both_core_and_an_extension() -> None:
    core = set(_TABLE_KEY.findall(protocol_section("request_core")))
    extensions = set(_TABLE_KEY.findall(protocol_section("request_extensions")))

    assert core & extensions == set()


@pytest.mark.parametrize("name", ["submit-message", "approval-response"])
def test_every_documented_example_validates(name: str) -> None:
    examples = _documented_examples()

    assert name in examples, sorted(examples)
    ChatRequestBody.model_validate(json.loads(examples[name]))


def test_the_submit_example_carries_the_user_message_the_turn_answers() -> None:
    body = ChatRequestBody.model_validate(
        json.loads(_documented_examples()["submit-message"]),
    )

    assert body.is_approval_resume is False
    assert body.last_user_text != ""
    assert str(body.last_user_message_id) == body.messages[-1].id


def test_the_approval_example_resumes_a_deferred_call() -> None:
    body = ChatRequestBody.model_validate(
        json.loads(_documented_examples()["approval-response"]),
    )

    assert body.is_approval_resume is True
    assert body.prior_assistant_message_id is not None
