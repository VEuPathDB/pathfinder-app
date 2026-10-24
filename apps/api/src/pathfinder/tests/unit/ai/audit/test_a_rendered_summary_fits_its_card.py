"""A synthesis summary that renders past the card's length is refused, and a stored one that does still reads."""

from __future__ import annotations

from pydantic_ai.messages import RetryPromptPart

from pathfinder.ai.audit.facts import audit_run_fact
from pathfinder.domain.audit.stages import RunStages
from pathfinder.domain.audit.verdicts import MAX_CARD, ReviewAgreement, StoredSynthesis
from pathfinder.services.audit.views import shown_synthesis
from pathfinder.tests.unit.ai.audit.test_synthesis import (
    _TRUNCATED,
    _draft,
    _first_then,
    _section,
    _stored,
    _synthesized,
    _view,
)

_FILLER = "The reviews keep the truncated models as errors and name their relatives. "


def _words(length: int) -> str:
    return (_FILLER * (length // len(_FILLER) + 1))[:length]


_CAUSE = _words(437)
_VIEW = _view().model_copy(update={"stages": RunStages(halted=_CAUSE)})
_FACT = audit_run_fact(_VIEW)
_CITE = f" [cite:{_FACT.id}.stages.halted]."
_SUMMARY = _words(1156 - len(_CITE)) + _CITE
_SHOWN = len(_SUMMARY) - len(_CITE) + len(f" ({_CAUSE}).")


def test_the_overflow_is_measured_on_the_rendered_summary() -> None:
    assert (len(_SUMMARY), len(_CAUSE), _SHOWN > MAX_CARD) == (1156, 437, True)


async def test_a_summary_that_renders_past_the_card_is_refused() -> None:
    retries: list[RetryPromptPart] = []
    wrong = _draft([_section(_TRUNCATED, 1, 2)], [1, 2], _SUMMARY)

    found = await _synthesized(
        [_stored(1), _stored(2)], _first_then(wrong, retries), _VIEW
    )

    (retry,) = retries
    assert str(retry.content).startswith(
        f"The summary reads {_SHOWN} characters once its references render, more "
        f"than {MAX_CARD}: shorten it, or cite fewer stored sentences."
    )
    assert found.summary == "Two kept."


def test_a_stored_summary_that_renders_past_the_card_still_reads() -> None:
    stored = StoredSynthesis(
        sections=(),
        headline=(),
        summary=_SUMMARY,
        agreement=ReviewAgreement(sampled=0, agreed=0),
        facts=(_FACT,),
    )

    shown = shown_synthesis(stored)

    assert (len(shown.summary), shown.summary[-len(_CAUSE) - 3 :]) == (
        _SHOWN,
        f"({_CAUSE}).",
    )
