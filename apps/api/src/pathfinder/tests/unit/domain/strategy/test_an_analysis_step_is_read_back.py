"""An exported analysis read back from the tree: hydration, replay and the
one-time statement of a criterion that carries the document."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.spec_hydration import (
    analysis_criteria_stated,
    spec_from_ast,
    spec_stating_the_live_tree,
)
from pathfinder.domain.strategy.spec_replay import spec_replaying

from ._analysis import (
    COMPUTE_SEARCH,
    DATASET,
    EXPORTED,
    WORDS,
    binding,
    document,
    exported_step,
)
from ._builders import combine

_TEXT = StrategyStepNode(id="step_t1", search_name="GenesByText")
_OTHER_DATASET = "DS_70dd50fed7"


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def test_a_hydrated_export_is_its_binding_and_states_no_parameter() -> None:
    spec = spec_from_ast(
        _ast(exported_step()), goal="g", analyses={EXPORTED: binding()}
    )

    criterion = spec.criteria[0]
    assert criterion.analysis == binding()
    assert (criterion.text, criterion.search_name) == (WORDS, COMPUTE_SEARCH)
    assert criterion.resolved_params == {}


def test_an_export_added_outside_is_stated_by_its_binding() -> None:
    spec = OperationalSpec(
        goal="g",
        criteria=[Criterion(id="step_t1", text="kinases", search_name="GenesByText")],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_t1")
        ),
    )
    live = _ast(combine("step_c1", _TEXT, exported_step()))

    stated = spec_stating_the_live_tree(
        spec, live, sheet_params={}, analyses={EXPORTED: binding()}
    )

    added = next(c for c in stated.criteria if c.id == EXPORTED)
    assert added.analysis == binding()
    assert added.resolved_params == {}


def test_a_cut_moved_on_the_site_takes_a_fresh_binding() -> None:
    answered = _ast(exported_step())
    live = _ast(exported_step(significance=0.01))
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(
                id=EXPORTED, text=WORDS, search_name=COMPUTE_SEARCH, analysis=binding()
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id=EXPORTED)),
    )

    replayed = spec_replaying(
        spec,
        outside_changes(answered, live),
        live,
        sheet_params={COMPUTE_SEARCH: frozenset({"eda_analysis_spec"})},
        analyses={EXPORTED: binding(significance=0.01)},
    )

    criterion = replayed.criteria[0]
    assert criterion.analysis is not None
    assert criterion.analysis.significance_threshold == 0.01
    assert criterion.resolved_params == {}


class TestTheOneTimeStatement:
    """A spec written before the binding existed states it at the turn entry."""

    def _carried(self) -> OperationalSpec:
        """The criterion an export wrote with its document as values."""
        return OperationalSpec(
            goal="g",
            criteria=[
                Criterion(
                    id=EXPORTED,
                    text="Genes higher in 24h than in 18h",
                    search_name=COMPUTE_SEARCH,
                    resolved_params={
                        "eda_dataset_id": StringValue(value=DATASET),
                        "eda_analysis_spec": document(),
                    },
                )
            ],
            structure=SpecStructure(
                root=StructureNode(kind="leaf", criterion_id=EXPORTED)
            ),
        )

    def test_the_criterion_gains_its_binding_and_drops_the_document(self) -> None:
        stated = analysis_criteria_stated(self._carried(), {EXPORTED: binding()})

        criterion = stated.criteria[0]
        assert criterion.analysis == binding()
        assert criterion.resolved_params == {}
        assert criterion.text == "Genes higher in 24h than in 18h"

    def test_a_second_statement_changes_nothing(self) -> None:
        analyses = {EXPORTED: binding()}
        once = analysis_criteria_stated(self._carried(), analyses)

        assert analysis_criteria_stated(once, analyses) is once

    def _with_a_drop_on(self, dataset: str) -> OperationalSpec:
        return self._carried().model_copy(
            update={
                "dropped": [
                    DroppedCriterion(
                        text="higher at 24 h than at 36 h",
                        reason="EDA-backed criterion",
                        eda_dataset_id=dataset,
                    )
                ]
            }
        )

    def test_a_drop_no_export_answers_waits_at_the_root(self) -> None:
        """The recorded drop named its dataset; it now waits for its analysis."""
        stated = analysis_criteria_stated(
            self._with_a_drop_on(_OTHER_DATASET), {EXPORTED: binding()}
        )

        waiting = stated.criteria[-1]
        assert (waiting.id, waiting.text, waiting.needs_analysis_on) == (
            f"c_{_OTHER_DATASET}",
            "higher at 24 h than at 36 h",
            _OTHER_DATASET,
        )
        assert stated.dropped == []
        assert stated.structure == SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=EXPORTED),
                    StructureNode(kind="leaf", criterion_id=f"c_{_OTHER_DATASET}"),
                ],
            )
        )

    def test_a_drop_an_export_on_its_dataset_answered_leaves(self) -> None:
        """An export on the drop's dataset answered it, so nothing waits."""
        stated = analysis_criteria_stated(
            self._with_a_drop_on(DATASET), {EXPORTED: binding()}
        )

        assert [c.id for c in stated.criteria] == [EXPORTED]
        assert (stated.dropped, stated.structure) == (
            [],
            SpecStructure(root=StructureNode(kind="leaf", criterion_id=EXPORTED)),
        )


class TestOneWaitingCriterionPerDataset:
    def _drop(self, text: str) -> DroppedCriterion:
        return DroppedCriterion(
            text=text, reason="EDA-backed criterion", eda_dataset_id=_OTHER_DATASET
        )

    def test_two_drops_on_one_dataset_fold_into_one_waiting_criterion(self) -> None:
        carried = TestTheOneTimeStatement()._carried()
        carried.dropped = [self._drop("24 h over 36 h"), self._drop("24 h over 12 h")]

        stated = analysis_criteria_stated(carried, {EXPORTED: binding()})

        assert [(c.id, c.text) for c in stated.criteria] == [
            (EXPORTED, "Genes higher in 24h than in 18h"),
            (f"c_{_OTHER_DATASET}", "24 h over 36 h"),
        ]
        assert stated.dropped == []

    def test_a_drop_beside_its_waiting_criterion_adds_no_second(self) -> None:
        carried = analysis_criteria_stated(
            TestTheOneTimeStatement()
            ._carried()
            .model_copy(update={"dropped": [self._drop("24 h over 36 h")]}),
            {EXPORTED: binding()},
        )
        carried.dropped = [self._drop("24 h over 12 h")]

        stated = analysis_criteria_stated(carried, {EXPORTED: binding()})

        assert [c.id for c in stated.criteria] == [EXPORTED, f"c_{_OTHER_DATASET}"]
        assert stated.dropped == []


def test_a_spec_that_names_one_criterion_twice_is_refused() -> None:
    twice = [
        {"id": "c_36", "text": "24 h over 36 h"},
        {"id": "c_36", "text": "24 h over 12 h"},
    ]

    with pytest.raises(ValidationError, match="c_36"):
        OperationalSpec.model_validate({"goal": "g", "criteria": twice})
