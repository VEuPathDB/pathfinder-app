"""Every refusal the edit and frame dispatches raise, and what it leaves behind.

The shared check runs the refusal, compares the committed spec, both baselines
and the strategy against what the dispatch found, and then lands a valid pass on
the same thread.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import ValidationError

from pathfinder.ai.lead import edit_dispatch
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    canvas_sets,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    declared,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead._refusal_checks import (
    a_refusal_that_keeps_the_thread_whole,
    thread_state,
)

_STRANGER = "c_stranger"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


async def _entered(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    return thread


def _binding_nothing() -> Draft:
    """A pass that recorded only why it gave up, and bound no criterion."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = []
        found.dropped = [
            DroppedCriterion(text="every criterion", reason="no realizable search")
        ]
        return found

    return _draft


def _unbound_criterion() -> Draft:
    """A criterion with no search behind it, which binds nothing at all."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [Criterion(id=_STRANGER, text="something vague")]
        found.structure = SpecStructure(root=leaf(_STRANGER))
        return found

    return _draft


def _silently_dropping_the_stage() -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != STAGE]
        found.structure = SpecStructure(root=leaf(SURFACE))
        return found

    return _draft


def _an_option_no_criterion_runs() -> Draft:
    """An option outside the structure whose search no live criterion carries."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria.append(
            Criterion(
                id=_STRANGER,
                text="from a search nothing here runs",
                search_name="GenesByChromosome",
                resolved_params={"chromosome": StringValue(value="6")},
            )
        )
        return found

    return _draft


async def test_a_pass_that_bound_nothing_is_refused_and_keeps_the_thread_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(
        _binding_nothing(),
        declared=declared("dropped", SURFACE, STAGE),
        disposition="needs_user",
    )

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "The edit pass left no spec behind" in refusal


async def test_a_pass_that_claimed_more_than_it_bound_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ready spec whose every criterion is unbound is a claim, not a spec."""
    thread = await _entered(monkeypatch)
    thread.frames(_unbound_criterion(), declared=declared("dropped", SURFACE, STAGE))

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "framed" in refusal


async def test_a_silent_drop_is_refused_before_anything_is_planned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(_silently_dropping_the_stage(), declared=kept(SURFACE))

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "This turn edits a spec that already had 2 criteria" in refusal
    assert f"{STAGE} (expressed in merozoites) is gone from the spec" in refusal


async def test_an_option_no_live_criterion_can_carry_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(_an_option_no_criterion_runs(), declared=kept(SURFACE, STAGE))

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "no criterion in the structure runs that search" in refusal
    assert f"{_STRANGER} (from a search nothing here runs) states chromosome" in (
        refusal
    )


async def test_a_strategy_changed_while_the_pass_ran_is_refused_by_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canvas commit that lands mid-pass makes the plan's base stale."""
    thread = await _entered(monkeypatch)
    found = thread_state(thread)
    thread.frames(
        with_the_proteome(2),
        declared=kept(SURFACE, STAGE),
        while_framing=lambda graph: canvas_sets(
            graph, SURFACE, min_signal=NumberValue(value=3)
        ),
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert "The strategy changed while this edit was being planned" in refusal
    assert thread.committed == []
    assert thread.spec == found.spec
    assert thread.before_turn == found.before_turn
    assert thread.facts()[SURFACE].parameters == {"min_signal": "3"}


async def test_a_commit_the_strategy_rejects_is_refused_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    found = thread_state(thread)

    async def _rejecting(**_kwargs: Any) -> CommitResult:
        msg = "the strategy has no root step to edit"
        raise ApplyError(msg)

    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _rejecting)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert "no root step to edit" in refusal
    assert thread_state(thread) == found
    assert thread.before_dispatch == found.spec


async def test_values_the_site_refuses_name_the_step_that_states_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    found = thread_state(thread)

    async def _refusing(**_kwargs: Any) -> CommitResult:
        raise ValidationError(
            title="Invalid",
            detail=f"{STAGE_PERCENTILE}: must be between 0 and 100.",
            errors=[
                {
                    "param": STAGE_PERCENTILE,
                    "messages": ["must be between 0 and 100."],
                }
            ],
        )

    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _refusing)
    thread.frames(
        with_the_percentile(900),
        declared=[*kept(SURFACE), *declared("changed", STAGE)],
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert f"[{STAGE}] GenesByRNASeqEvidence" in refusal
    assert STAGE_PERCENTILE in refusal
    assert thread_state(thread) == found


def _a_second_root_adopted() -> Draft:
    """The structure joins a step that stands outside the strategy it edits."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria.append(
            Criterion(id=PROTEOME, text="a loose step", search_name="GenesByMassSpec")
        )
        assert found.structure is not None
        found.structure = SpecStructure(
            root=joined(CombineOp.INTERSECT, found.structure.root, leaf(PROTEOME))
        )
        return found

    return _draft


async def test_an_edit_that_would_adopt_a_loose_step_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step outside the edited strategy stays outside it."""
    loose = StrategyStepNode(id=PROTEOME, search_name="GenesByMassSpec")
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree(), loose),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    thread.frames(_a_second_root_adopted(), declared=kept(SURFACE, STAGE))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert f"the edit would adopt ['{PROTEOME}']" in refusal
    assert thread.committed == []
    assert thread.graph.steps[PROTEOME].primary_input_id is None
