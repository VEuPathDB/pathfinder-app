"""What the newest check of a run found against the request, in the words the
check gives each gap and caveat."""

from __future__ import annotations

from pydantic import Field
from pydantic_ai.messages import ModelMessage

from pathfinder.ai.models.mock.reads import ToolAnswer, last_return

VERIFY = "verify_strategy"
GAPS_LEAD = "The check found what the strategy does not answer:"
CAVEATS_LEAD = "The check measured:"


class _Worded(ToolAnswer):
    sentence: str


class _Found(ToolAnswer):
    gaps: list[_Worded] = Field(default_factory=list)
    caveats: list[_Worded] = Field(default_factory=list)


class _Checked(ToolAnswer):
    digest: _Found = Field(default_factory=_Found)


def _checked(messages: list[ModelMessage]) -> _Found:
    read = last_return(messages, VERIFY, _Checked)
    return _Found() if read is None else read.digest


def gap_sentences(messages: list[ModelMessage]) -> list[str]:
    return [gap.sentence for gap in _checked(messages).gaps]


def caveat_sentences(messages: list[ModelMessage]) -> list[str]:
    return [caveat.sentence for caveat in _checked(messages).caveats]


def _paragraph(lead: str, sentences: list[str]) -> str:
    return f"{lead} {' '.join(f'{s}.' for s in sentences)}" if sentences else ""


def gap_paragraph(messages: list[ModelMessage]) -> str:
    """Each gap of the newest check in one paragraph, or nothing."""
    return _paragraph(GAPS_LEAD, gap_sentences(messages))


def caveat_paragraph(messages: list[ModelMessage]) -> str:
    """Each caveat of the newest check in one paragraph, or nothing."""
    return _paragraph(CAVEATS_LEAD, caveat_sentences(messages))


def findings(messages: list[ModelMessage]) -> str:
    """The gaps, then the caveats, of the newest check, or nothing when the
    check found none."""
    found = [gap_paragraph(messages), caveat_paragraph(messages)]
    return "".join(f"\n\n{paragraph}" for paragraph in found if paragraph)
