"""Spec and strategy disagreements whose edit ends with wrong data or a wrong account.

Each test states the outcome the researcher is owed, over the production
refresh and edit dispatch.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.tools import DeferredToolResults
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
)
from veupathdb.errors import ValidationError

from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import record_the_spec_the_dispatch_found
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    structure_criteria,
)
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    proteome,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
    surface_step,
)

_EXPORTED = "step_5e6f7a8b"
_EXPORT_ROOT = "step_6f7a8b9c"
_FIRST = "c_first"
_SECOND = "c_second"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


async def test_a_value_set_in_the_editor_survives_an_edit_of_another_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edit moves one value of the step, and the step keeps its others."""
    thread = _thread(monkeypatch)
    thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] = NumberValue(value=48)
    await thread.next_turn()
    thread.frames(with_the_percentile(90), declared=[])

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.graph.steps[STAGE].parameters[STAGE_TIMEPOINT] == NumberValue(
        value=48
    )


async def test_a_resumed_edit_does_not_rebuild_a_step_deleted_while_it_was_parked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch)
    await thread.next_turn()
    record_the_spec_the_dispatch_found(thread.deps, resume=None)
    thread.session.graph = session_holding(surface_step()).graph
    await thread.next_turn(resumes_parked_call=True)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    await thread.edit(resume=SubAgentResume(messages=[], results=DeferredToolResults()))

    assert [step_id for step_id in thread.graph.steps if step_id == STAGE] == []


async def test_the_delta_accounts_for_the_step_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A criterion framed last turn reads changed in the diff, and a step was added."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(with_the_proteome(None), declared=[], disposition="needs_user")
    await thread.edit()
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert delta.diff.added_count == 0
    account = delta.model_dump(exclude={"diff", "preserved_step_ids"})
    assert [name for name, value in account.items() if value == [PROTEOME]] != []


def _two_new(second: float | None) -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id not in {_FIRST, _SECOND}]
        found.criteria.append(
            Criterion(
                id=_FIRST,
                text="first",
                search_name="GenesByFirst",
                resolved_params={"threshold_first": NumberValue(value=1)},
            )
        )
        found.criteria.append(
            Criterion(
                id=_SECOND,
                text="second",
                search_name="GenesBySecond",
                resolved_params={}
                if second is None
                else {"threshold_second": NumberValue(value=second)},
                open_params=[]
                if second is not None
                else [OpenSlot(criterion_id=_SECOND, param_name="threshold_second")],
            )
        )
        assert found.structure is not None
        if _FIRST not in structure_criteria(found.structure):
            found.structure = SpecStructure(
                root=joined(
                    CombineOp.INTERSECT,
                    found.structure.root,
                    leaf(_FIRST),
                    leaf(_SECOND),
                )
            )
        return found

    return _draft


async def test_a_refused_value_names_the_new_step_that_states_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diff calls the unbuilt criterion kept, and this edit still writes it."""
    thread = _thread(monkeypatch)
    await thread.next_turn()
    thread.frames(_two_new(None), declared=[], disposition="needs_user")
    await thread.edit()

    async def _refusing(**_kwargs: Any) -> CommitResult:
        raise ValidationError(
            title="Invalid",
            detail="threshold_first: Cannot be empty.",
            errors=[{"param": "threshold_first", "messages": ["Cannot be empty."]}],
        )

    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _refusing)
    await thread.next_turn()
    thread.frames(_two_new(3), declared=kept(SURFACE, STAGE, _FIRST, _SECOND))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    named = [cid for cid in (_FIRST, _SECOND) if f"[{cid}]" in refusal]
    assert named == [_FIRST]


def _thread_with_an_export_beside_a_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> DisagreementThread:
    """An exported step joined at the root while the structure is still a plan."""
    tree = StrategyStepNode(
        id=_EXPORT_ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=built_tree(),
        secondary_input=StrategyStepNode(id=_EXPORTED, search_name="GenesByEdaSubset"),
    )
    spec = built_spec()
    assert spec.structure is not None
    spec.criteria.append(proteome(None))
    spec.criteria.append(
        Criterion(id=_EXPORTED, text="the subset", search_name="GenesByEdaSubset")
    )
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, spec.structure.root, leaf(PROTEOME))
    )
    return DisagreementThread(
        monkeypatch,
        spec=spec,
        session=session_holding(tree),
        recorded_build=recorded(SURFACE, STAGE, ROOT, _EXPORTED, _EXPORT_ROOT),
    )


async def test_a_live_step_the_structure_leaves_out_is_never_called_an_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal asks for a structure, and never for the live step's drop."""
    thread = _thread_with_an_export_beside_a_plan(monkeypatch)
    await thread.next_turn()
    thread.frames(
        with_the_proteome(2), declared=kept(SURFACE, STAGE, PROTEOME, _EXPORTED)
    )

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert "drop_criterion" not in refusal
