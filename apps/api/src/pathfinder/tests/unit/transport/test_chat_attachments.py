"""The chat route refuses an attachment the model that reads the message
cannot read, before the message is stored or a model is called."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.conversation.attachments import ReadAttachment
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import AttachmentNotReadableError, ErrorCode
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID, SITE_HELP_ASSISTANT_ID
from pathfinder.transport.http.routers.chat import refuse_unreadable_attachments

_PNG = "data:image/png;base64,iVBORw0KGgo="
_READ = ReadAttachment(filename="t.png", media_type="image/png", size=8)


def _body(**overrides: object) -> ChatRequestBody:
    message = {
        "id": str(uuid4()),
        "role": "user",
        "parts": [
            {"type": "text", "text": "which genes are in this image?"},
            {
                "type": "file",
                "mediaType": "image/png",
                "filename": "t.png",
                "url": _PNG,
            },
        ],
    }
    return ChatRequestBody.model_validate(
        {"conversationId": str(uuid4()), "siteId": "plasmodb", "messages": [message]}
        | overrides
    )


@pytest.fixture
def anthropic_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "anthropic")
    monkeypatch.setattr(settings, "default_tier", "balanced")


@pytest.mark.usefixtures("anthropic_default")
def test_an_image_is_refused_when_the_default_lead_does_not_read_images() -> None:
    with pytest.raises(AttachmentNotReadableError) as refused:
        refuse_unreadable_attachments(_body(), PATHFINDER_ASSISTANT_ID)

    assert refused.value.code == ErrorCode.ATTACHMENT_NOT_READABLE
    assert refused.value.detail is not None
    assert refused.value.detail.startswith("Claude Sonnet 5 does not read images;")


@pytest.mark.usefixtures("anthropic_default")
def test_an_image_passes_when_the_lead_is_picked_on_a_model_that_reads_it() -> None:
    body = _body(phaseModels={"lead": "openai:gpt-5.6-luna"})

    assert refuse_unreadable_attachments(body, PATHFINDER_ASSISTANT_ID) == [_READ]


@pytest.mark.usefixtures("anthropic_default")
def test_a_pick_for_another_role_does_not_decide_what_the_reader_reads() -> None:
    body = _body(phaseModels={"frame": "openai:gpt-5.6-luna"})

    with pytest.raises(AttachmentNotReadableError):
        refuse_unreadable_attachments(body, PATHFINDER_ASSISTANT_ID)


@pytest.mark.usefixtures("anthropic_default")
def test_the_site_help_agent_is_the_reader_of_its_own_turns() -> None:
    body = _body(phaseModels={SITE_HELP_ASSISTANT_ID: "google:gemini-3.6-flash"})

    assert refuse_unreadable_attachments(body, SITE_HELP_ASSISTANT_ID) == [_READ]


def test_a_message_without_files_reads_none() -> None:
    body = ChatRequestBody.model_validate(
        {"conversationId": str(uuid4()), "siteId": "plasmodb", "messages": []}
    )

    assert refuse_unreadable_attachments(body, PATHFINDER_ASSISTANT_ID) == []
