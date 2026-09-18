"""A saved strategy whose root is a combine reaches WDK as a combine.

The shapes here are the wire form of a three-step PlasmoDB strategy: a signal
peptide search INTERSECT an RNA-seq search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
    clone_with_fresh_ids,
    flatten_tree,
    subtree_ids,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
    WDKStrategyDetails,
)
from veupathdb_mcp.catalog import ValidatedParams
from veupathdb_mcp.wdk import build_snapshot_from_wdk

from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.services.strategies import spec_build, step_wdk_push
from pathfinder.services.strategies.step_search import (
    names_a_wdk_question,
    states_a_question,
)
from pathfinder.services.strategies.sync_state import WDKSyncState

_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
_SIGNAL = "GenesWithSignalPeptide"
_RNASEQ = "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC"
_LEFT_KEY = "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass"
_RIGHT_KEY = "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass"
_SIGNAL_WDK_ID = 440483013
_RNASEQ_WDK_ID = 440483023
_COMBINE_WDK_ID = 440483033
_BQ_REFUSAL = "bq_operator: Cannot be empty."


def _saved_strategy() -> WDKStrategyDetails:
    """The wire form of the saved strategy, with the counts the site reports."""
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330659633,
            "rootStepId": _COMBINE_WDK_ID,
            "name": "Gametocyte combine block",
            "recordClassName": "transcript",
            "stepTree": {
                "stepId": _COMBINE_WDK_ID,
                "primaryInput": {"stepId": _SIGNAL_WDK_ID},
                "secondaryInput": {"stepId": _RNASEQ_WDK_ID},
            },
            "steps": {
                str(_SIGNAL_WDK_ID): {
                    "id": _SIGNAL_WDK_ID,
                    "searchName": _SIGNAL,
                    "displayName": "Predicted Signal Peptide",
                    "estimatedSize": 572,
                    "searchConfig": {
                        "parameters": {
                            "organism": '["Plasmodium falciparum 3D7"]',
                            "signalp_version": "SignalP-4.1",
                        }
                    },
                },
                str(_RNASEQ_WDK_ID): {
                    "id": _RNASEQ_WDK_ID,
                    "searchName": _RNASEQ,
                    "displayName": "RNA-Seq (fold change)",
                    "estimatedSize": 1566,
                    "searchConfig": {
                        "parameters": {
                            "regulated_dir": "up-regulated",
                            "fold_change": "3",
                        }
                    },
                },
                str(_COMBINE_WDK_ID): {
                    "id": _COMBINE_WDK_ID,
                    "searchName": _BOOLEAN,
                    "displayName": "Combine Gene results",
                    "estimatedSize": 142,
                    "searchConfig": {
                        "parameters": {
                            "bq_operator": "INTERSECT",
                            _LEFT_KEY: str(_SIGNAL_WDK_ID),
                            _RIGHT_KEY: str(_RNASEQ_WDK_ID),
                        }
                    },
                },
            },
        }
    )


def _single_step_strategy() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330659611,
            "rootStepId": _SIGNAL_WDK_ID,
            "name": "Gametocyte signal peptide block",
            "recordClassName": "transcript",
            "stepTree": {"stepId": _SIGNAL_WDK_ID},
            "steps": {
                str(_SIGNAL_WDK_ID): {
                    "id": _SIGNAL_WDK_ID,
                    "searchName": _SIGNAL,
                    "estimatedSize": 572,
                    "searchConfig": {
                        "parameters": {
                            "organism": '["Plasmodium falciparum 3D7"]',
                            "signalp_version": "SignalP-4.1",
                        }
                    },
                },
            },
        }
    )


def _cloned_nodes(saved: WDKStrategyDetails) -> list[StrategyStep]:
    """The steps the insert path pushes, in dependency order."""
    ast, _wire = build_snapshot_from_wdk(saved)
    root = clone_with_fresh_ids(ast.root)
    steps = flatten_tree(root)
    return [steps[step_id] for step_id in subtree_ids(root.id, steps)]


@dataclass
class RecordingAPI:
    """Records every WDK write and hands back the site's own step ids."""

    created: list[NewStepSpec] = field(default_factory=list)
    combined: list[CombinedStepSpec] = field(default_factory=list)
    patched: list[str] = field(default_factory=list)
    next_id: int = 500000001

    async def create_step(self, spec: NewStepSpec, **_kw: Any) -> WDKIdentifier:
        self.created.append(spec)
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def create_combined_step(
        self, spec: CombinedStepSpec, **_kw: Any
    ) -> WDKIdentifier:
        self.combined.append(spec)
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def create_transform_step(
        self, spec: NewStepSpec, *_args: Any, **_kw: Any
    ) -> WDKIdentifier:
        self.created.append(spec)
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def update_step_properties(self, *_args: Any, **_kw: Any) -> None:
        return None

    async def update_step_search_config(self, **_kw: Any) -> None:
        self.patched.append("update_step_search_config")

    async def find_step(self, step_id: int, **_kw: Any) -> WDKStep:
        return WDKStep(
            id=step_id,
            search_name=_SIGNAL,
            search_config=WDKSearchConfig(parameters={}),
        )


@dataclass
class _Validations:
    """The search names the push asked the catalog to validate."""

    names: list[str] = field(default_factory=list)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> RecordingAPI:
    recorder = RecordingAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: recorder)
    return recorder


@pytest.fixture
def validated(monkeypatch: pytest.MonkeyPatch) -> _Validations:
    """Answer the catalog the way the site does, refusing the boolean question."""
    seen = _Validations()

    async def _validate(
        search: Any, *, parameters: Any, callbacks: Any
    ) -> ValidatedParams:
        del callbacks
        seen.names.append(search.search_name)
        if search.search_name == _BOOLEAN:
            raise ValidationError(title="invalid parameters", detail=_BQ_REFUSAL)
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(spec_build, "validate_parameters", _validate)
    monkeypatch.setattr(spec_build, "make_validation_callbacks", lambda _site: None)
    return seen


async def _push(nodes: list[StrategyStep]) -> BuildOutcome:
    outcome = BuildOutcome()
    await spec_build._push_tree_to_wdk(
        nodes=nodes,
        graph_record_type="transcript",
        site_id="plasmodb",
        sync_state=WDKSyncState(),
        outcome=outcome,
    )
    return outcome


class TestTheCombineReachesWDKAsACombine:
    async def test_the_clone_keeps_the_kind_and_the_operator(self) -> None:
        nodes = _cloned_nodes(_saved_strategy())

        combine = nodes[-1]
        assert combine.kind is StepKind.COMBINE
        assert combine.operator is CombineOp.INTERSECT
        assert combine.search_name == _BOOLEAN

    async def test_every_step_pushes(
        self, api: RecordingAPI, validated: _Validations
    ) -> None:
        del validated

        outcome = await _push(_cloned_nodes(_saved_strategy()))

        assert outcome.failed_steps == []
        assert len(outcome.pushed_step_ids) == 3

    async def test_the_operator_reaches_the_combined_step_call(
        self, api: RecordingAPI, validated: _Validations
    ) -> None:
        del validated

        await _push(_cloned_nodes(_saved_strategy()))

        assert len(api.combined) == 1
        assert api.combined[0].boolean_operator is CombineOp.INTERSECT
        assert [spec.search_name for spec in api.created] == [_SIGNAL, _RNASEQ]

    async def test_the_boolean_question_is_never_validated_as_a_search(
        self, api: RecordingAPI, validated: _Validations
    ) -> None:
        del api

        await _push(_cloned_nodes(_saved_strategy()))

        assert validated.names == [_SIGNAL, _RNASEQ]


class TestASingleStepSavedStrategy:
    async def test_it_pushes_one_leaf_and_no_combine(
        self, api: RecordingAPI, validated: _Validations
    ) -> None:
        outcome = await _push(_cloned_nodes(_single_step_strategy()))

        assert outcome.failed_steps == []
        assert len(outcome.pushed_step_ids) == 1
        assert [spec.search_name for spec in api.created] == [_SIGNAL]
        assert api.combined == []
        assert validated.names == [_SIGNAL]


class TestASetOperationIsNeverPushedAsASearch:
    def _orphaned_combine(self) -> StrategyStep:
        """A combine that lost both inputs and reads as a leaf under its name."""
        node = StrategyStepNode(id="step_971a7e05", search_name=_BOOLEAN)
        return flatten_tree(node)["step_971a7e05"]

    async def test_the_leaf_push_refuses_it_by_name(self, api: RecordingAPI) -> None:
        step = self._orphaned_combine()

        wdk_id, _validation, failure = await step_wdk_push.push_step_to_wdk(
            sync_state=WDKSyncState(),
            step=step,
            site_id="plasmodb",
            record_type="transcript",
            search_name=_BOOLEAN,
            parameters={},
        )

        assert wdk_id is None
        assert failure is not None
        assert failure.step_id == "step_971a7e05"
        assert "set operation pushed as a search" in failure.error
        assert _BOOLEAN in failure.error
        assert api.created == []

    async def test_the_transform_push_refuses_it_by_name(
        self, api: RecordingAPI
    ) -> None:
        node = StrategyStepNode(
            id="step_half",
            search_name=_BOOLEAN,
            primary_input=StrategyStepNode(id="step_a", search_name=_SIGNAL),
        )
        step = flatten_tree(node)["step_half"]

        wdk_id, _validation, failure = await step_wdk_push.push_step_to_wdk(
            sync_state=WDKSyncState(wdk_step_ids={"step_a": _SIGNAL_WDK_ID}),
            step=step,
            site_id="plasmodb",
            record_type="transcript",
            search_name=_BOOLEAN,
            parameters={},
        )

        assert wdk_id is None
        assert failure is not None
        assert "set operation pushed as a search" in failure.error
        assert api.created == []

    async def test_the_patch_refuses_it_by_name(self, api: RecordingAPI) -> None:
        step = self._orphaned_combine()
        sync_state = WDKSyncState(wdk_step_ids={step.id: _COMBINE_WDK_ID})

        failure = await step_wdk_push._execute_patch(
            sync_state, "plasmodb", step, "transcript", name_moved=False
        )

        assert failure is not None
        assert "set operation pushed as a search" in failure.error
        assert api.patched == []


class TestTheQuestionPredicate:
    def test_a_combine_wdk_named_states_no_question(self) -> None:
        nodes = _cloned_nodes(_saved_strategy())

        assert names_a_wdk_question(nodes[-1]) is False
        assert names_a_wdk_question(nodes[0]) is True

    def test_the_ast_sentinel_states_no_question(self) -> None:
        assert states_a_question(COMBINE_SEARCH_NAME) is False
        assert states_a_question(_BOOLEAN) is False
        assert states_a_question("") is False
        assert states_a_question(_SIGNAL) is True
