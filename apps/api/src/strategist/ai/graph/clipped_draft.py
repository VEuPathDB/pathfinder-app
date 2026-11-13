from __future__ import annotations

from typing import Annotated

from assistant_core.memory.schemas import MemoryEntryDraft
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BeforeValidator, ConfigDict, Field, ValidationError

from strategist.domain.clipped import list_clipped_to, text_clipped_to


class _DraftWords(CamelModel):
    model_config = ConfigDict(extra="allow")

    name: Annotated[str, text_clipped_to(200)]
    summary: Annotated[str, text_clipped_to(400)]
    tags: Annotated[list[str], list_clipped_to(8)] = Field(default_factory=list)


def clipped_draft(raw: object) -> object:
    try:
        return _DraftWords.model_validate(raw).model_dump(by_alias=True)
    except ValidationError:
        return raw


type ClippedDraft = Annotated[MemoryEntryDraft, BeforeValidator(clipped_draft)]
