"""The files a message may carry to the model that reads it, and the caps on them."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict
from pydantic_ai import BinaryContent
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart

from pathfinder.ai.models.catalog import ModelEntry, get_model_catalog
from pathfinder.platform.errors import (
    AttachmentNotReadableError,
    AttachmentTooLargeError,
)

_MIB = 1024 * 1024
MAX_FILE_BYTES = 10 * _MIB
MAX_MESSAGE_BYTES = 20 * _MIB
MAX_ATTACHMENTS = 6

IMAGE_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
DOCUMENT_MEDIA_TYPES = frozenset({"application/pdf"})

_KINDS_READ = "PNG, JPEG, WebP and GIF images and PDF documents"


class ReadAttachment(BaseModel):
    """One attachment a turn takes: its name, its kind and its decoded size."""

    model_config = ConfigDict(frozen=True)

    filename: str
    media_type: str
    size: int


def _megabytes(size: int) -> str:
    return f"{size / _MIB:.1f} MB"


@dataclass(frozen=True)
class _Kind:
    noun: str
    media_types: frozenset[str]
    read_by: Callable[[ModelEntry], bool]


_KINDS = (
    _Kind("images", IMAGE_MEDIA_TYPES, lambda m: m.supports_images),
    _Kind("PDFs", DOCUMENT_MEDIA_TYPES, lambda m: m.supports_documents),
)


def _check_kind(part: FileUIPart, name: str, model: ModelEntry) -> None:
    kind = next((k for k in _KINDS if part.media_type in k.media_types), None)
    if kind is None:
        msg = f"{name} is {part.media_type}; PathFinder reads {_KINDS_READ}."
        raise AttachmentNotReadableError(msg)
    if kind.read_by(model):
        return
    readers = [m.name for m in get_model_catalog() if kind.read_by(m)]
    msg = (
        f"{model.name} does not read {kind.noun}; choose a model that does in "
        f"Settings: {', '.join(readers)}."
    )
    raise AttachmentNotReadableError(msg)


def _read_one(part: FileUIPart, model: ModelEntry) -> ReadAttachment:
    name = part.filename or "the attachment"
    _check_kind(part, name, model)
    if not part.url.startswith("data:"):
        msg = f"{name} is a link; an attachment is sent inline."
        raise AttachmentNotReadableError(msg)
    try:
        content = BinaryContent.from_data_uri(part.url)
    except ValueError as err:
        msg = f"{name} is not a readable data URL."
        raise AttachmentNotReadableError(msg) from err
    size = len(content.data)
    if size > MAX_FILE_BYTES:
        msg = (
            f"{name} is {_megabytes(size)}; one attachment can be at most "
            f"{MAX_FILE_BYTES // _MIB} MB."
        )
        raise AttachmentTooLargeError(msg)
    return ReadAttachment(filename=name, media_type=part.media_type, size=size)


def read_attachments(
    parts: Sequence[FileUIPart], model: ModelEntry
) -> list[ReadAttachment]:
    """The attachments of one message, each one readable by ``model``.

    :raises AttachmentTooLargeError: A file, or the message, is over its cap.
    :raises AttachmentNotReadableError: ``model`` cannot read a file's kind.
    """
    if len(parts) > MAX_ATTACHMENTS:
        msg = (
            f"One message can carry at most {MAX_ATTACHMENTS} attachments; "
            f"this one has {len(parts)}."
        )
        raise AttachmentTooLargeError(msg)
    read = [_read_one(part, model) for part in parts]
    total = sum(a.size for a in read)
    if total > MAX_MESSAGE_BYTES:
        msg = (
            f"These attachments come to {_megabytes(total)}; one message can carry "
            f"at most {MAX_MESSAGE_BYTES // _MIB} MB."
        )
        raise AttachmentTooLargeError(msg)
    return read


__all__ = [
    "DOCUMENT_MEDIA_TYPES",
    "IMAGE_MEDIA_TYPES",
    "MAX_ATTACHMENTS",
    "MAX_FILE_BYTES",
    "MAX_MESSAGE_BYTES",
    "ReadAttachment",
    "read_attachments",
]
