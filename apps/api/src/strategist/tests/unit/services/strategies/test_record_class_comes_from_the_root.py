"""A step is addressed under its own record class, and the strategy's is the
root's.

The pin is the class-crossing transform. On plasmodb, ``GenesByMolecularWeight``
is listed under ``transcript`` and ``GenesFromTranscripts`` ("Transform
Transcripts to Genes") is listed under ``gene``. Each 404s under the other::

    curl 'https://qa.plasmodb.org/plasmo.qa/service/record-types/gene/searches/GenesByMolecularWeight'
    404 There is no search "GenesByMolecularWeight" associated with record type "GeneRecordClass"

    curl 'https://qa.plasmodb.org/plasmo.qa/service/record-types/transcript/searches/GenesFromTranscripts'
    404 There is no search "GenesFromTranscripts" associated with record type "TranscriptRecordClass"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    record_class_of,
)
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from veupathdb_mcp.catalog import (
    ValidatedParams,
    ValidationCallbacks,
    assign_step_record_classes,
)

from strategist.services.strategies import commit_tree, record_classes
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.wdk_write_stubs import skip_the_tree_put

_LISTED_UNDER = {
    "GenesByMolecularWeight": "transcript",
    "GenesByExonCount": "transcript",
    "GenesFromTranscripts": "gene",
    "TranscriptsFromGenes": "transcript",
}


async def _catalog_resolver(search_name: str) -> str | None:
    return _LISTED_UNDER.get(search_name)


def _leaf(step_id: str, search: str, record_class: str | None = None) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.SEARCH,
        search_name=search,
        record_class=record_class,
    )


def _transform(
    step_id: str, search: str, input_id: str, record_class: str | None = None
) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.TRANSFORM,
        search_name=search,
        primary_input_id=input_id,
        record_class=record_class,
    )


def _combine(step_id: str, primary: str, secondary: str) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.COMBINE,
        primary_input_id=primary,
        secondary_input_id=secondary,
        operator=CombineOp.INTERSECT,
    )


class TestTheStrategysClassIsTheRoots:
    def test_a_class_crossing_transform_makes_the_strategy_its_own_class(self) -> None:
        steps = {
            "leaf": _leaf("leaf", "GenesByMolecularWeight", "transcript"),
            "root": _transform("root", "GenesFromTranscripts", "leaf", "gene"),
        }

        assert record_class_of("root", steps) == "gene"
        assert record_class_of("leaf", steps) == "transcript"

    def test_a_combine_takes_the_class_of_the_steps_it_consumes(self) -> None:
        steps = {
            "a": _leaf("a", "GenesByMolecularWeight", "transcript"),
            "b": _leaf("b", "GenesByExonCount", "transcript"),
            "and": _combine("and", "a", "b"),
        }

        assert record_class_of("and", steps) == "transcript"

    def test_a_step_whose_search_did_not_resolve_has_no_class(self) -> None:
        steps = {
            "leaf": _leaf("leaf", "GenesByNothing"),
            "known": _leaf("known", "GenesByMolecularWeight", "transcript"),
            "and": _combine("and", "leaf", "known"),
        }

        assert [record_class_of(sid, steps) for sid in ("leaf", "known", "and")] == [
            None,
            "transcript",
            "transcript",
        ]

    def test_a_cycle_does_not_hang(self) -> None:
        a = _combine("a", "b", "b")
        b = StrategyStep(id="b", kind=StepKind.TRANSFORM, primary_input_id="a")

        assert [record_class_of(sid, {"a": a, "b": b}) for sid in "ab"] == [None, None]


class TestEachStepTakesTheClassItsSearchIsListedUnder:
    async def test_the_catalog_gives_every_step_its_own(self) -> None:
        steps = {
            "leaf": _leaf("leaf", "GenesByMolecularWeight"),
            "root": _transform("root", "GenesFromTranscripts", "leaf"),
        }

        await assign_step_record_classes(steps, _catalog_resolver)

        assert steps["leaf"].record_class == "transcript"
        assert steps["root"].record_class == "gene"

    async def test_a_combine_is_left_for_its_inputs_to_answer(self) -> None:
        steps = {
            "a": _leaf("a", "GenesByMolecularWeight"),
            "b": _leaf("b", "GenesByExonCount"),
            "and": _combine("and", "a", "b"),
        }

        await assign_step_record_classes(steps, _catalog_resolver)

        assert steps["and"].record_class is None
        assert record_class_of("and", steps) == "transcript"


@dataclass
class _RecordingAPI:
    next_id: int = 2000
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(("create_step", spec.search_name, record_type))
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id, input_step_id
        self.calls.append(("create_transform_step", spec.search_name, record_type))
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del user_id, spec
        self.calls.append(("create_combined_step", "", record_type))
        return WDKIdentifier(id=self._alloc())

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByMolecularWeight",
            search_config=WDKSearchConfig(parameters={}),
        )


async def _as_stated(*_args: object, **kwargs: Any) -> ValidatedParams:
    return ValidatedParams(params=dict(kwargs["stated"]))


async def _commit(steps: dict[str, StrategyStep]) -> CommittedTree:
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=steps,
        root_id="root",
        old=None,
        sync_state=WDKSyncState(),
        target=commit_tree.CommitTarget(name="crossing", description=""),
    )


@pytest.fixture
def recording_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    api = _RecordingAPI()
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", _as_stated)
    skip_the_tree_put(monkeypatch)
    return api


class TestThePushAddressesEachStepByItsOwn:
    async def test_the_leaf_and_the_transform_go_to_different_record_types(
        self, recording_api: _RecordingAPI
    ) -> None:
        committed = await _commit(
            {
                "leaf": _leaf("leaf", "GenesByMolecularWeight", "transcript"),
                "root": _transform("root", "GenesFromTranscripts", "leaf", "gene"),
            }
        )

        assert committed.failures == []
        assert recording_api.calls == [
            ("create_step", "GenesByMolecularWeight", "transcript"),
            ("create_transform_step", "GenesFromTranscripts", "gene"),
        ]


class TestValidationWritesTheClassOntoTheStep:
    async def test_the_step_keeps_the_class_validation_resolved(
        self, recording_api: _RecordingAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        del recording_api

        async def _validate(ctx: Any, **_kwargs: object) -> ValidatedParams:
            return ValidatedParams(
                params={}, record_class=_LISTED_UNDER[ctx.search_name]
            )

        async def _resolve(
            record_type: str | None,
            search_name: str | None,
        ) -> str | None:
            del record_type
            return _LISTED_UNDER.get(search_name or "")

        async def _hint(search_name: str, exclude: str | None = None) -> str | None:
            del search_name, exclude
            return None

        async def _resolver(_site_id: str) -> Any:
            return _catalog_resolver

        monkeypatch.setattr(commit_tree, "validate_parameters", _validate)
        monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
        monkeypatch.setattr(
            commit_tree,
            "make_validation_callbacks",
            lambda _site_id: ValidationCallbacks(
                resolve_record_type_for_search=_resolve,
                find_record_type_hint=_hint,
            ),
        )

        steps = {
            "leaf": _leaf("leaf", "GenesByMolecularWeight"),
            "root": _transform("root", "GenesFromTranscripts", "leaf"),
        }
        committed = await _commit(steps)

        assert (committed.drafts, committed.failures) == ({}, [])
        assert steps["leaf"].record_class == "transcript"
        assert steps["root"].record_class == "gene"
