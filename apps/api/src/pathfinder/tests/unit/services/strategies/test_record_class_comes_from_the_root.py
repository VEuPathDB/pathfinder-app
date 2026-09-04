"""A step is addressed under its own record class, and the strategy's is the
root's.

The pin is the class-crossing transform. On plasmodb, ``GenesByMolecularWeight``
is listed under ``transcript`` and ``GenesFromTranscripts`` ("Transform
Transcripts to Genes") is listed under ``gene``. Each 404s under the other::

    curl 'https://plasmodb.org/plasmo/service/record-types/gene/searches/GenesByMolecularWeight'
    404 There is no search "GenesByMolecularWeight" associated with record type "GeneRecordClass"

    curl 'https://plasmodb.org/plasmo/service/record-types/transcript/searches/GenesFromTranscripts'
    404 There is no search "GenesFromTranscripts" associated with record type "TranscriptRecordClass"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pathfinder.domain.strategy.graph_model import (
    StepKind,
    StrategyStep,
    record_class_of,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.integrations.veupathdb.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from pathfinder.services.catalog.param_validation import (
    ValidatedParams,
    ValidationCallbacks,
)
from pathfinder.services.catalog.searches import assign_step_record_classes
from pathfinder.services.strategies import step_wdk_push
from pathfinder.services.strategies.step_push_planner import CreateAction, StepPushPlan
from pathfinder.services.strategies.step_wdk_push import push_steps_with_plan
from pathfinder.services.strategies.sync_state import WDKSyncState

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

        assert record_class_of("root", steps, fallback="transcript") == "gene"
        assert record_class_of("leaf", steps, fallback="transcript") == "transcript"

    def test_a_combine_takes_the_class_of_the_steps_it_consumes(self) -> None:
        steps = {
            "a": _leaf("a", "GenesByMolecularWeight", "transcript"),
            "b": _leaf("b", "GenesByExonCount", "transcript"),
            "and": _combine("and", "a", "b"),
        }

        assert record_class_of("and", steps, fallback="gene") == "transcript"

    def test_a_step_whose_search_did_not_resolve_takes_the_fallback(self) -> None:
        steps = {"leaf": _leaf("leaf", "GenesByNothing")}

        assert record_class_of("leaf", steps, fallback="transcript") == "transcript"

    def test_a_cycle_does_not_hang(self) -> None:
        a = _combine("a", "b", "b")
        b = StrategyStep(id="b", kind=StepKind.TRANSFORM, primary_input_id="a")

        assert record_class_of("a", {"a": a, "b": b}, fallback="gene") == "gene"


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
        assert record_class_of("and", steps, fallback="gene") == "transcript"


@dataclass
class _RecordingAPI:
    next_id: int = 2000
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
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


async def _noop_validate_plan_params(*_args: object, **_kwargs: object) -> set[str]:
    return set()


@pytest.fixture
def recording_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    api = _RecordingAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(
        step_wdk_push, "_validate_plan_params", _noop_validate_plan_params
    )
    return api


class TestThePushAddressesEachStepByItsOwn:
    async def test_the_leaf_and_the_transform_go_to_different_record_types(
        self, recording_api: _RecordingAPI
    ) -> None:
        graph = StrategyGraph("g1", "crossing", "plasmodb")
        graph.steps = {
            "leaf": _leaf("leaf", "GenesByMolecularWeight", "transcript"),
            "root": _transform("root", "GenesFromTranscripts", "leaf", "gene"),
        }
        graph.record_type = "gene"
        graph.recompute_roots()

        plan = [
            StepPushPlan(step_id="leaf", action=CreateAction(), reason="new"),
            StepPushPlan(step_id="root", action=CreateAction(), reason="new"),
        ]
        outcome = await push_steps_with_plan(graph, WDKSyncState(), "plasmodb", plan)

        assert outcome.failed == []
        assert recording_api.calls == [
            ("create_step", "GenesByMolecularWeight", "transcript"),
            ("create_transform_step", "GenesFromTranscripts", "gene"),
        ]


class TestValidationWritesTheClassOntoTheStep:
    async def test_the_step_keeps_the_class_validation_resolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

        monkeypatch.setattr(step_wdk_push, "validate_parameters", _validate)
        monkeypatch.setattr(
            step_wdk_push,
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
        plan = [
            StepPushPlan(step_id="leaf", action=CreateAction(), reason="new"),
            StepPushPlan(step_id="root", action=CreateAction(), reason="new"),
        ]

        incomplete = await step_wdk_push._validate_plan_params(
            plan, steps, "plasmodb", "transcript", {}
        )

        assert incomplete == set()
        assert steps["leaf"].record_class == "transcript"
        assert steps["root"].record_class == "gene"
