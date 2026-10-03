"""An edit pass whose only change removes a built step is sent to the card."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.turn_records import NamedStep
from pathfinder.ai.lead.edit_messages import removal_is_the_cards_message
from pathfinder.domain.strategy.operational_spec import OperationalSpec, SpecStructure
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead._refusal_checks import (
    a_refusal_that_keeps_the_thread_whole,
)


def _dropping(*criterion_ids: str) -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id not in criterion_ids]
        kept = [c.id for c in found.criteria]
        found.structure = SpecStructure(root=leaf(kept[0]))
        return found

    return _draft


async def _entered(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    return thread


async def test_a_removal_only_pass_is_refused_and_keeps_the_thread_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(
        _dropping(STAGE),
    )

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert refusal == (
        f"This edit only removes [{STAGE}] 'merozoite stage' "
        "(GenesByRNASeqEvidence), and a removal is the researcher's to approve. "
        "Nothing was applied: the strategy still holds every step and every "
        "value it held before this edit. "
        f'Call delete_step with step_id "{STAGE}"; its card names the step and '
        "the researcher approves it. Do not dispatch edit_strategy to remove a "
        "step."
    )


def test_several_removed_steps_are_each_named_for_one_card_at_a_time() -> None:
    message = removal_is_the_cards_message(
        {
            "step_a": NamedStep(title="signal peptide", search_name="GenesBySP"),
            "step_b": NamedStep(title="tm domains", search_name="GenesByTM"),
        }
    )

    assert message == (
        "This edit only removes each of [step_a] 'signal peptide' (GenesBySP), "
        "[step_b] 'tm domains' (GenesByTM), and a removal is the researcher's to "
        "approve. Nothing was applied: the strategy still holds every step and "
        "every value it held before this edit. Call delete_step once for each of "
        'step_id "step_a", "step_b", one card at a time; each card names its step '
        "and the researcher approves it. Do not dispatch edit_strategy to remove "
        "a step."
    )
