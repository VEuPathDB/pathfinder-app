"""An undo returns the strategy to the revision before the last change, with no FRAME pass."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ToolFailed
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, pre_turn
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operations import (
    GraphOperation,
    UpdateCombineOperatorOp,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import StrategyRevisionView
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_UNDO = "Undo that, keep the intersection."
_BEFORE_THE_FLIP = 39
_AFTER_THE_FLIP = 884


def _leaf(step_id: str, search_name: str, value: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "searchName": search_name,
        "parameters": {"organism": {"type": "string", "value": value}},
    }


def _tree(root_operator: CombineOp) -> StrategyAst:
    """``root_operator(expression, INTERSECT(signal peptide, TM))``."""
    return StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "name": "secreted and expressed",
            "root": {
                "id": "root",
                "operator": root_operator.value,
                "primaryInput": _leaf("expression", "GenesByRNASeqEvidence", "3D7"),
                "secondaryInput": {
                    "id": "inner",
                    "operator": "INTERSECT",
                    "primaryInput": _leaf("signal", "GenesBySignalPeptide", "3D7"),
                    "secondaryInput": _leaf("tm", "GenesByTransmembraneDomains", "3D7"),
                },
            },
        }
    )


def _session(root_operator: CombineOp) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="secreted", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_tree(root_operator).root)
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={"root": _AFTER_THE_FLIP})
    return session


def _stored(ast: StrategyAst) -> StrategyRevisionView:
    return StrategyRevisionView(
        id=7,
        conversation_id=uuid4(),
        revision=strategy_revision(ast),
        record_type="transcript",
        strategy_ast=ast.model_dump(by_alias=True, mode="json", exclude_none=True),
        step_count=5,
        created_at=datetime.now(UTC),
    )


def _no_session() -> AsyncSession:
    """A session bound to no database; the revision read is replaced."""
    return AsyncSession()


class _Undo:
    """One undo turn over the flipped tree, with its FRAME pass and commit captured."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        stored: StrategyAst | None,
        intent: UserIntent,
    ) -> None:
        self.framed = False
        self.ops: list[GraphOperation] = []
        session = _session(CombineOp.UNION)
        state = pipeline_state(user_prompt=_UNDO, domain=StrategyDomainState())
        state.user_message_id = uuid4()
        self.deps: LeadDeps = lead_deps(state, intent=intent, strategy_session=session)
        self.deps.runtime = replace(self.deps.runtime, db_session_factory=_no_session)
        self.deps.state.turn_markers.record_arrival("root", {"root": _AFTER_THE_FLIP})

        async def _previous(*_args: Any, **_kwargs: Any) -> StrategyRevisionView | None:
            return None if stored is None else _stored(stored)

        async def _frame(**_kwargs: Any) -> FrameResult:
            self.framed = True
            return FrameResult(disposition="spec_ready", summary="reframed")

        async def _commit(*, ops: list[GraphOperation], **_kwargs: Any) -> CommitResult:
            self.ops = ops
            graph = session.graph
            assert graph is not None
            graph.steps["root"].operator = CombineOp.INTERSECT
            assert session.sync_state is not None
            session.sync_state.step_counts["root"] = _BEFORE_THE_FLIP
            return CommitResult(description="root set to INTERSECT")

        async def _no_sheets(**_kwargs: Any) -> dict[str, Any]:
            return {}

        async def _no_marks(*_args: Any) -> dict[str, str]:
            return {}

        monkeypatch.setattr(edit_dispatch, "previous_revision", _previous)
        monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
        monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
        monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
        monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _no_sheets)
        monkeypatch.setattr(pre_turn, "organism_parameters", _no_marks)

    async def run(self) -> EditDelta:
        result = await run_edit(deps=self.deps, parent_tool_call_id="t1", reason=_UNDO)
        assert isinstance(result, EditDelta)
        return result


def _undo_intent(
    *constraints: Constraint, withdrawn: tuple[Constraint, ...] = ()
) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="undo the last change",
        undo=True,
        explicit_constraints=list(constraints),
        withdrawn=list(withdrawn),
    )


def _combination(value: str, source: ConstraintSource) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        label="combination",
        requested_value=value,
        source=source,
    )


_WITHDRAWN_UNION = _combination(
    "surface features OR blood-stage expression", ConstraintSource.ASSUMED
)
_KEPT_INTERSECTION = _combination(
    "surface features AND blood-stage expression", ConstraintSource.USER_EXPLICIT
)


async def test_the_undo_flips_the_root_back_and_touches_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(monkeypatch, stored=_tree(CombineOp.INTERSECT), intent=_undo_intent())

    await undo.run()

    assert undo.ops == [
        UpdateCombineOperatorOp(step_id="root", operator=CombineOp.INTERSECT)
    ]


async def test_an_undo_that_withdraws_the_change_it_undoes_runs_no_frame_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An undo withdraws the last change by nature, so the withdrawal keeps it an undo."""
    undo = _Undo(
        monkeypatch,
        stored=_tree(CombineOp.INTERSECT),
        intent=_undo_intent(_KEPT_INTERSECTION, withdrawn=(_WITHDRAWN_UNION,)),
    )

    await undo.run()

    assert (undo.framed, undo.ops) == (
        False,
        [UpdateCombineOperatorOp(step_id="root", operator=CombineOp.INTERSECT)],
    )


async def test_the_undo_runs_no_frame_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    undo = _Undo(monkeypatch, stored=_tree(CombineOp.INTERSECT), intent=_undo_intent())

    await undo.run()

    assert undo.framed is False


async def test_the_undo_s_delta_says_the_structure_moved_and_no_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(monkeypatch, stored=_tree(CombineOp.INTERSECT), intent=_undo_intent())

    delta = await undo.run()

    assert (delta.diff.structure_changed, delta.diff.kept_count) == (True, 3)
    assert delta.operations_applied == 1


async def test_the_facts_show_the_count_before_and_after_the_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(monkeypatch, stored=_tree(CombineOp.INTERSECT), intent=_undo_intent())

    await undo.run()

    facts = turn_facts(undo.deps)
    assert (facts.root_count_before, facts.root_count) == (
        _AFTER_THE_FLIP,
        _BEFORE_THE_FLIP,
    )


async def test_an_undo_to_the_tree_the_strategy_holds_is_nothing_to_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(monkeypatch, stored=_tree(CombineOp.UNION), intent=_undo_intent())

    with pytest.raises(ToolFailed) as failed:
        await undo.run()

    assert failed.value.message.startswith("Nothing to undo")
    assert undo.ops == []


async def test_an_undo_on_the_first_strategy_has_nothing_to_return_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(monkeypatch, stored=None, intent=_undo_intent())

    with pytest.raises(ToolFailed) as failed:
        await undo.run()

    assert "no strategy before" in failed.value.message
    assert undo.ops == []


async def test_an_undo_that_states_a_new_value_is_framed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A message that names a value is an edit to frame, whatever else it says."""
    undo = _Undo(
        monkeypatch,
        stored=_tree(CombineOp.INTERSECT),
        intent=_undo_intent(
            Constraint(
                kind=ConstraintKind.ORGANISM,
                label="organism",
                requested_value="P. vivax",
            )
        ),
    )

    await undo.run()

    assert undo.framed is True


async def test_an_undo_that_withdraws_and_states_an_organism_is_framed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undo = _Undo(
        monkeypatch,
        stored=_tree(CombineOp.INTERSECT),
        intent=_undo_intent(
            Constraint(
                kind=ConstraintKind.ORGANISM,
                label="organism",
                requested_value="P. vivax",
            ),
            withdrawn=(_WITHDRAWN_UNION,),
        ),
    )

    await undo.run()

    assert undo.framed is True


async def test_an_undo_no_criterion_can_state_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A previous tree that differs only in a weight is not an edit, and the
    spec the dispatch found stands."""
    weighted = _tree(CombineOp.UNION)
    expression = weighted.root.primary_input
    assert expression is not None
    weighted.root.primary_input = expression.model_copy(update={"wdk_weight": 10})
    undo = _Undo(monkeypatch, stored=weighted, intent=_undo_intent())

    with pytest.raises(ToolFailed) as failed:
        await undo.run()

    assert failed.value.message.startswith("Nothing to undo that an edit can state")
    assert undo.deps.state.domain.operational_spec == (
        undo.deps.state.domain.spec_before_dispatch
    )
