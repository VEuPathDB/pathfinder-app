"""The turn entry reads every exported analysis as a binding: a cut moved on
the site, a criterion written before bindings existed, and a strategy no spec
describes."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.tests._support.analysis_catalog import serve_the_catalog
from pathfinder.tests._support.eda_step_doubles import DE_DATASET
from pathfinder.tests.unit.ai.lead._analysis_thread import (
    WAITING,
    document,
    with_the_waiting_comparison,
)
from pathfinder.tests.unit.ai.lead._disagreement_site import (
    install_the_site,
    site_sets,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    joined,
    kept,
    leaf,
    session_holding,
)

_EXPORTED = "step_2c6dce8d"
_WORDS = "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)"


def _exported_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=_EXPORTED,
        search_name=COMPUTE_QUERY,
        display_name="Genes higher in 24h than in 18h",
        parameters={
            "eda_dataset_id": StringValue(value=DE_DATASET),
            "eda_analysis_spec": document("18h", 0.05),
        },
    )


def _carried() -> OperationalSpec:
    """The criterion an export wrote before a binding existed: the document."""
    return OperationalSpec(
        goal="24 h over 18 h",
        criteria=[
            Criterion(
                id=_EXPORTED,
                text="Genes higher in 24h than in 18h",
                search_name=COMPUTE_QUERY,
                resolved_params=dict(_exported_step().parameters),
            )
        ],
        structure=SpecStructure(root=leaf(_EXPORTED)),
    )


def _thread(
    monkeypatch: pytest.MonkeyPatch, spec: OperationalSpec
) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch, spec=spec, session=session_holding(_exported_step())
    )


async def test_a_cut_moved_on_the_site_is_the_criterions_new_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch, _carried())
    await thread.next_turn()
    site = install_the_site(thread)
    site_sets(site, _EXPORTED, eda_analysis_spec=document("18h", 0.01))

    await thread.next_turn()

    [criterion] = thread.spec.criteria
    assert criterion.analysis is not None
    assert criterion.analysis.significance_threshold == 0.01
    assert criterion.resolved_params == {}
    assert thread.answered.criteria[0].analysis == criterion.analysis


async def test_a_criterion_that_carries_the_document_is_stated_by_its_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch, _carried())

    await thread.next_turn()

    for spec in (thread.spec, thread.answered, thread.before_turn):
        [criterion] = spec.criteria
        assert criterion.analysis is not None
        assert criterion.analysis.words == _WORDS
        assert criterion.resolved_params == {}


async def test_an_edit_after_the_statement_proceeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch, _carried())
    await thread.next_turn()
    thread.frames(with_the_waiting_comparison(_EXPORTED), declared=kept(_EXPORTED))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert (delta.operations_applied, thread.committed) == (0, [])
    assert [c.id for c in thread.spec.criteria] == [_EXPORTED, WAITING]


async def test_a_strategy_no_spec_describes_is_stated_by_its_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread(monkeypatch, OperationalSpec())
    thread.deps.state.domain.operational_spec = None

    await thread.next_turn()

    [criterion] = thread.spec.criteria
    assert criterion.analysis is not None
    assert (criterion.id, criterion.text) == (_EXPORTED, _WORDS)
    assert criterion.resolved_params == {}


_OTHER_DATASET = "DS_70dd50fed7"


def _drop(dataset: str) -> DroppedCriterion:
    return DroppedCriterion(
        text="higher at 24 h than at 36 h",
        reason="EDA-backed criterion",
        eda_dataset_id=dataset,
    )


def _records(thread: DisagreementThread) -> dict[str, list[str]]:
    """The criterion ids of the four specs the turn holds."""
    domain = thread.deps.state.domain
    held = {
        "plan": domain.operational_spec,
        "answered": domain.answered_spec,
        "before_turn": domain.spec_before_turn,
        "before_dispatch": domain.spec_before_dispatch,
    }
    return {
        name: [] if spec is None else [c.id for c in spec.criteria]
        for name, spec in held.items()
    }


async def test_a_drop_on_a_dataset_no_export_answers_waits_at_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    carried = _carried()
    carried.dropped = [_drop(_OTHER_DATASET)]
    thread = _thread(monkeypatch, carried)

    await thread.next_turn()

    assert [(c.id, c.needs_analysis_on) for c in thread.spec.criteria] == [
        (_EXPORTED, None),
        (f"c_{_OTHER_DATASET}", _OTHER_DATASET),
    ]
    assert thread.spec.dropped == []
    assert thread.spec.structure == SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(_EXPORTED), leaf(f"c_{_OTHER_DATASET}"))
    )


async def test_a_dispatch_record_that_still_carries_an_answered_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The export on that dataset answered the drop, so no record waits on it."""
    thread = _thread(monkeypatch, _carried())
    stale = _carried()
    stale.dropped = [_drop(DE_DATASET)]
    thread.deps.state.domain.spec_before_dispatch = stale

    await thread.next_turn()

    assert _records(thread) == {
        "plan": [_EXPORTED],
        "answered": [_EXPORTED],
        "before_turn": [_EXPORTED],
        "before_dispatch": [_EXPORTED],
    }
    assert thread.before_dispatch.dropped == []


async def test_the_statement_changes_nothing_on_the_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    carried = _carried()
    carried.dropped = [_drop(_OTHER_DATASET)]
    thread = _thread(monkeypatch, carried)
    thread.deps.state.domain.spec_before_dispatch = carried.model_copy(deep=True)
    await thread.next_turn()
    first = thread.deps.state.domain.model_copy(deep=True)

    await thread.next_turn()

    domain = thread.deps.state.domain
    assert (
        domain.operational_spec,
        domain.answered_spec,
        domain.spec_before_turn,
        domain.spec_before_dispatch,
    ) == (
        first.operational_spec,
        first.answered_spec,
        first.spec_before_turn,
        first.spec_before_dispatch,
    )


async def test_a_stored_step_with_no_kind_is_stamped_once_at_the_turn_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A strategy stored before kinds existed reads the catalog, then carries it."""
    thread = _thread(monkeypatch, _carried())
    read = serve_the_catalog(monkeypatch)
    assert thread.graph.words.analysis_kinds == {}

    await thread.next_turn()
    await thread.next_turn()

    assert thread.graph.words.analysis_kinds == {
        _EXPORTED: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }
    assert read == [COMPUTE_QUERY]
    answered = thread.deps.state.domain.answered_graph
    assert answered is not None
    assert StepWords.of(answered).analysis_kinds == {
        _EXPORTED: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }
