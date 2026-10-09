"""An attachment reaches a turn only when the model that reads the message can
read its kind, and only within the size caps the event log can hold."""

from __future__ import annotations

import base64

import pytest
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart

from pathfinder.ai.conversation.attachments import (
    MAX_ATTACHMENTS,
    MAX_FILE_BYTES,
    ReadAttachment,
    read_attachments,
)
from pathfinder.platform.errors import (
    AttachmentNotReadableError,
    AttachmentTooLargeError,
    ErrorCode,
)
from pathfinder.platform.model_catalog import ModelEntry, get_model_entry
from pathfinder.tests._support.models import DEFAULT_MODEL

_MIB = 1024 * 1024


def _model(model_id: str) -> ModelEntry:
    entry = get_model_entry(model_id)
    assert entry is not None
    return entry


READER = _model(DEFAULT_MODEL)
BLIND = _model("mock:deterministic")


def _part(media_type: str, size: int, filename: str = "table.png") -> FileUIPart:
    encoded = base64.b64encode(b"\0" * size).decode()
    return FileUIPart(
        media_type=media_type,
        filename=filename,
        url=f"data:{media_type};base64,{encoded}",
    )


def test_an_image_and_a_pdf_within_the_caps_are_read() -> None:
    parts = [_part("image/png", 1000), _part("application/pdf", 2000, "paper.pdf")]

    assert read_attachments(parts, READER) == [
        ReadAttachment(filename="table.png", media_type="image/png", size=1000),
        ReadAttachment(filename="paper.pdf", media_type="application/pdf", size=2000),
    ]


def test_a_file_over_the_per_file_cap_is_refused_as_too_large() -> None:
    with pytest.raises(AttachmentTooLargeError) as refused:
        read_attachments([_part("image/png", MAX_FILE_BYTES + 2 * _MIB)], READER)

    assert refused.value.status == 413
    assert refused.value.code == ErrorCode.ATTACHMENT_TOO_LARGE
    assert (
        refused.value.detail
        == "table.png is 12.0 MB; one attachment can be at most 10 MB."
    )


def test_a_message_over_the_total_cap_is_refused_as_too_large() -> None:
    parts = [_part("image/png", 8 * _MIB, f"{n}.png") for n in range(3)]

    with pytest.raises(AttachmentTooLargeError) as refused:
        read_attachments(parts, READER)

    assert refused.value.detail == (
        "These attachments come to 24.0 MB; one message can carry at most 20 MB."
    )


def test_more_attachments_than_the_cap_are_refused() -> None:
    parts = [_part("image/png", 10, f"{n}.png") for n in range(MAX_ATTACHMENTS + 1)]

    with pytest.raises(AttachmentTooLargeError) as refused:
        read_attachments(parts, READER)

    assert (
        refused.value.detail
        == "One message can carry at most 6 attachments; this one has 7."
    )


def test_an_image_is_refused_for_a_model_that_does_not_read_images() -> None:
    with pytest.raises(AttachmentNotReadableError) as refused:
        read_attachments([_part("image/png", 10)], BLIND)

    assert refused.value.status == 422
    assert refused.value.code == ErrorCode.ATTACHMENT_NOT_READABLE
    assert refused.value.detail is not None
    assert refused.value.detail.startswith(
        f"{BLIND.name} does not read images; choose a model that does in Settings: "
    )
    assert READER.name in refused.value.detail


def test_a_pdf_is_refused_for_a_model_that_does_not_read_documents() -> None:
    with pytest.raises(AttachmentNotReadableError) as refused:
        read_attachments([_part("application/pdf", 10, "paper.pdf")], BLIND)

    assert refused.value.detail is not None
    assert refused.value.detail.startswith(f"{BLIND.name} does not read PDFs;")


def test_a_kind_no_model_reads_here_is_refused() -> None:
    with pytest.raises(AttachmentNotReadableError) as refused:
        read_attachments([_part("text/html", 10, "page.html")], READER)

    assert refused.value.detail == (
        "page.html is text/html; PathFinder reads PNG, JPEG, WebP and GIF images "
        "and PDF documents."
    )


def test_a_file_that_is_not_inline_is_refused() -> None:
    linked = FileUIPart(
        media_type="image/png", filename="far.png", url="https://example.org/far.png"
    )

    with pytest.raises(AttachmentNotReadableError) as refused:
        read_attachments([linked], READER)

    assert refused.value.detail == "far.png is a link; an attachment is sent inline."
