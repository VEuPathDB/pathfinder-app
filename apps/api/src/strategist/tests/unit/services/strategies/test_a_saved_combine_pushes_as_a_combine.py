"""A saved strategy whose root is a combine reaches WDK as a combine.

The shapes here are the wire form of a three-step PlasmoDB strategy: a signal
peptide search INTERSECT an RNA-seq search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
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
    WDKStrategyDetails,
)
from veupathdb_mcp.catalog import ValidatedParams
from veupathdb_mcp.wdk import build_snapshot_from_wdk

from strategist.services.strategies import commit_tree
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.step_push_planner import PatchAction
from strategist.services.strategies.step_search import (
    names_a_wdk_question,
    states_a_question,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist.tests._support.wdk_write_stubs import (
    commit_against,
)

_VALUES = PatchAction(search_config=True, name=False)

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


class RecordingAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__(next_id=500000001)

    @property
    def created(self) -> list[str]:
        return [
            call.kwargs["search_name"]
            for call in self.calls
            if call.name in {"create_step", "create_transform_step"}
        ]

    @property
    def combined(self) -> list[str]:
        return [
            call.kwargs["boolean_operator"]
            for call in self.named("create_combined_step")
        ]

    @property
    def patched(self) -> list[str]:
        return [call.name for call in self.named("update_step_search_config")]


@dataclass
class _Validations:
    """The search names the push asked the catalog to validate."""

    names: list[str] = field(default_factory=list)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> RecordingAPI:
    recorder = RecordingAPI()
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: recorder)
    list_every_search_under(monkeypatch, "transcript")
    return recorder


@pytest.fixture
def validated(monkeypatch: pytest.MonkeyPatch) -> _Validations:
    """Answer the catalog the way the site does, refusing the boolean question."""
    seen = _Validations()

    async def _validate(
        search: Any,
        *,
        stated: Any,
        context: Any,
        held_validation: Any,
        callbacks: Any,
        about: Any,
    ) -> ValidatedParams:
        del context, held_validation, callbacks, about
        seen.names.append(search.search_name)
        if search.search_name == _BOOLEAN:
            raise ValidationError(title="invalid parameters", detail=_BQ_REFUSAL)
        return ValidatedParams(params=dict(stated))

    monkeypatch.setattr(commit_tree, "validate_parameters", _validate)
    monkeypatch.setattr(commit_tree, "make_validation_callbacks", lambda _site: None)
    return seen


async def _push(nodes: list[StrategyStep]) -> CommittedTree:
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps={node.id: node for node in nodes},
        root_id=nodes[-1].id,
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget(name="saved", description=""),
    )


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

        committed = await _push(_cloned_nodes(_saved_strategy()))

        assert (committed.failures, committed.drafts) == ([], {})
        assert len(committed.pushed) == 3

    async def test_the_operator_reaches_the_combined_step_call(
        self, api: RecordingAPI, validated: _Validations
    ) -> None:
        del validated

        await _push(_cloned_nodes(_saved_strategy()))

        assert api.combined == [CombineOp.INTERSECT.value]
        assert api.created == [_SIGNAL, _RNASEQ]

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
        committed = await _push(_cloned_nodes(_single_step_strategy()))

        assert (committed.failures, committed.drafts) == ([], {})
        assert len(committed.pushed) == 1
        assert api.created == [_SIGNAL]
        assert api.combined == []
        assert validated.names == [_SIGNAL]


class TestASetOperationIsNeverPushedAsASearch:
    def _orphaned_combine(self) -> StrategyStepNode:
        """A combine that lost both inputs and reads as a leaf under its name."""
        return StrategyStepNode(id="step_971a7e05", search_name=_BOOLEAN)

    async def test_the_leaf_push_refuses_it_by_name(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        committed, _ = await commit_against(
            monkeypatch, api, self._orphaned_combine(), before=None, held={}
        )

        (failure,) = committed.failures
        assert failure.step_id == "step_971a7e05"
        assert "set operation pushed as a search" in failure.error
        assert _BOOLEAN in failure.error
        assert api.created == []

    async def test_the_transform_push_refuses_it_by_name(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node = StrategyStepNode(
            id="step_half",
            search_name=_BOOLEAN,
            primary_input=StrategyStepNode(id="step_a", search_name=_SIGNAL),
        )

        committed, _ = await commit_against(
            monkeypatch,
            api,
            node,
            before=node.model_copy(update={"id": "step_before"}),
            held={"step_a": _SIGNAL_WDK_ID},
        )

        (failure,) = committed.failures
        assert "set operation pushed as a search" in failure.error
        assert api.created == []

    async def test_the_patch_refuses_it_by_name(
        self, api: RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        step = self._orphaned_combine()
        before = step.model_copy(
            update={"parameters": {"bq_operator": StringValue(value="UNION")}}
        )

        committed, _ = await commit_against(
            monkeypatch, api, step, before=before, held={step.id: _COMBINE_WDK_ID}
        )

        (failure,) = committed.failures
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
