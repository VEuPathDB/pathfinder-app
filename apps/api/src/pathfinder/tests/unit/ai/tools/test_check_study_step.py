"""``check_study_step`` reads the cut a study step was built with."""

from __future__ import annotations

import json
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.eda import EdaPermissionEntry, EdaStudyDetail

from pathfinder.ai.tools.standalone import strategy_graph
from pathfinder.ai.tools.standalone.strategy_graph import (
    StrategySummaryResponse,
    StudyStepCheck,
    check_study_step,
    get_strategy,
)
from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.catalog import UnknownEdaDatasetError
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.eda_doubles import permission_entry, study_of
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET, PHENOTYPE_ENTITY
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_STEP_ID = "step_af9d7803"
_MFS_VARIABLE = "EUPATH_0000731"
_RECORD_COUNT = 3984
_MFS_SENTENCE = "Mutant Fitness Score is between -4.094 and -2.0"
_SPECIES_VARIABLE = "VAR_035294d0"


def _mfs_descriptor(*, filtered: bool) -> list[dict[str, Any]]:
    if not filtered:
        return []
    return [
        {
            "entityId": PHENOTYPE_ENTITY,
            "variableId": _MFS_VARIABLE,
            "type": "numberRange",
            "min": -4.094,
            "max": -2.0,
        },
    ]


def _subset_spec(*, filtered: bool) -> str:
    descriptor = _mfs_descriptor(filtered=filtered)
    return json.dumps(
        {
            "studyId": PHENOTYPE_DATASET,
            "displayName": "Essential in blood stages",
            "descriptor": {"subset": {"descriptor": descriptor}, "computations": []},
        },
    )


def _volcano_spec(*, filtered: bool = False) -> str:
    return json.dumps(
        {
            "studyId": PHENOTYPE_DATASET,
            "displayName": "Febrile against normal",
            "descriptor": {
                "subset": {"descriptor": _mfs_descriptor(filtered=filtered)},
                "computations": [
                    {
                        "computationId": "de2",
                        "descriptor": {
                            "type": "differentialexpression",
                            "configuration": {
                                "identifierVariable": {
                                    "entityId": PHENOTYPE_ENTITY,
                                    "variableId": "VEUPATHDB_GENE_ID",
                                },
                                "valueVariable": {
                                    "entityId": PHENOTYPE_ENTITY,
                                    "variableId": "READ_COUNT",
                                },
                                "comparator": {
                                    "variable": {
                                        "entityId": PHENOTYPE_ENTITY,
                                        "variableId": "VAR_state",
                                    },
                                    "groupA": [{"label": "normal"}],
                                    "groupB": [{"label": "febrile"}],
                                },
                            },
                        },
                        "visualizations": [
                            {
                                "visualizationId": "v2",
                                "displayName": "Volcano",
                                "descriptor": {
                                    "type": "volcanoplot",
                                    "configuration": {
                                        "effectSizeThreshold": 1,
                                        "significanceThreshold": 0.05,
                                    },
                                },
                            },
                        ],
                    },
                ],
            },
        },
    )


def _mfs_study() -> EdaStudyDetail:
    return study_of(
        [
            {
                "id": _MFS_VARIABLE,
                "displayName": "Mutant Fitness Score",
                "type": "number",
                "dataShape": "continuous",
            },
            {
                "id": _SPECIES_VARIABLE,
                "displayName": "Species",
                "type": "string",
                "dataShape": "categorical",
            },
        ],
        entity_id=PHENOTYPE_ENTITY,
    )


@pytest.fixture(autouse=True)
def _serve_the_study(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _detail(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        return permission_entry(), _mfs_study()

    monkeypatch.setattr(strategy_graph, "get_study_detail_for_dataset", _detail)


def _session(spec: str, *, search_name: str) -> StrategySession:
    """A session holding one study step, with the count a sync read."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "Essential kinases", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(
        flatten_tree(
            StrategyStepNode(
                id=_STEP_ID,
                search_name=search_name,
                parameters={
                    "eda_dataset_id": StringValue(value=PHENOTYPE_DATASET),
                    "eda_analysis_spec": StringValue(value=spec),
                },
            ),
        ),
    )
    graph.recompute_roots()
    graph.note_analysis_kinds(
        {
            _STEP_ID: StampedKind(
                search_name=search_name,
                kind=AnalysisKind.SUBSET
                if search_name == "GenesByEdaSubset"
                else AnalysisKind.COMPUTE,
            )
        }
    )
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={_STEP_ID: _RECORD_COUNT})
    return session


async def _check(spec: str, *, search_name: str = "GenesByEdaSubset") -> StudyStepCheck:
    ctx = agent_run_context(strategy_session=_session(spec, search_name=search_name))
    answer = await check_study_step(ctx, _STEP_ID)
    return returned(answer, StudyStepCheck)


async def _summary(spec: str, *, search_name: str = "GenesByEdaSubset") -> str:
    ctx = agent_run_context(strategy_session=_session(spec, search_name=search_name))
    answer = await check_study_step(ctx, _STEP_ID)
    return str(summary_of(answer).data["summary"])


class TestASubsetStep:
    async def test_the_filters_are_reported_as_the_sheet_writes_them(self) -> None:
        check = await _check(_subset_spec(filtered=True))

        assert check.subset_filters == [_MFS_SENTENCE]
        assert check.thresholds is None
        assert check.record_count == _RECORD_COUNT

    async def test_the_summary_names_the_count_and_the_first_filter(self) -> None:
        summary = await _summary(_subset_spec(filtered=True))

        assert summary == f"3,984 records, 1 filter: {_MFS_SENTENCE}"

    async def test_a_subset_with_no_filter_is_the_whole_subset(self) -> None:
        spec = _subset_spec(filtered=False)

        check = await _check(spec)

        assert check.subset_filters == []
        assert await _summary(spec) == "3,984 records, whole subset"


class TestAComputeStep:
    async def test_the_thresholds_stand_and_no_filter_is_reported(self) -> None:
        check = await _check(_volcano_spec(), search_name="GenesByEdaVizWithCompute")

        assert check.subset_filters == []
        assert check.thresholds is not None
        assert check.thresholds.significance_threshold == 0.05
        assert check.fold_change_threshold == 2.0

    async def test_the_check_names_the_comparison_its_method_and_its_side(
        self,
    ) -> None:
        check = await _check(_volcano_spec(), search_name="GenesByEdaVizWithCompute")

        assert check.comparison == EdaComparison(
            group_a=["normal"], group_b=["febrile"]
        )
        assert (check.method, check.effect_direction) == ("DESeq", "upAndDown")

    async def test_the_summary_names_the_cut_and_the_comparison(self) -> None:
        summary = await _summary(
            _volcano_spec(), search_name="GenesByEdaVizWithCompute"
        )

        assert summary == (
            "3,984 records at 2-fold and p 0.05, DESeq: genes that differ "
            "between normal and febrile"
        )

    async def test_the_strategy_read_states_the_step_by_what_it_selects(
        self,
    ) -> None:
        session = _session(_volcano_spec(), search_name="GenesByEdaVizWithCompute")

        answer = await get_strategy(agent_run_context(strategy_session=session))

        assert returned(answer, StrategySummaryResponse).analyses == {
            _STEP_ID: (
                "Genes that differ between normal and febrile (DESeq, "
                "|effect| >= 1, p <= 0.05)"
            )
        }


class TestAComputeStepThatWasAlsoFiltered:
    """The normal flow filters, computes and exports, so both cuts are read."""

    async def test_both_the_thresholds_and_the_filter_are_reported(self) -> None:
        check = await _check(
            _volcano_spec(filtered=True), search_name="GenesByEdaVizWithCompute"
        )

        assert check.subset_filters == [_MFS_SENTENCE]
        assert check.thresholds is not None
        assert check.thresholds.significance_threshold == 0.05

    async def test_the_summary_leads_with_the_thresholds(self) -> None:
        summary = await _summary(
            _volcano_spec(filtered=True), search_name="GenesByEdaVizWithCompute"
        )

        assert summary == (
            "3,984 records at 2-fold and p 0.05, DESeq: genes that differ "
            "between normal and febrile, 1 filter"
        )


class TestTwoFilters:
    async def test_the_summary_counts_them_and_names_the_first(self) -> None:
        spec = json.dumps(
            {
                "studyId": PHENOTYPE_DATASET,
                "displayName": "Essential in blood stages",
                "descriptor": {
                    "subset": {
                        "descriptor": [
                            *_mfs_descriptor(filtered=True),
                            {
                                "entityId": PHENOTYPE_ENTITY,
                                "variableId": _SPECIES_VARIABLE,
                                "type": "stringSet",
                                "stringSet": ["P. berghei"],
                            },
                        ],
                    },
                    "computations": [],
                },
            },
        )

        check = await _check(spec)

        assert check.subset_filters == [
            _MFS_SENTENCE,
            "Species is one of P. berghei",
        ]
        assert await _summary(spec) == f"3,984 records, 2 filters: {_MFS_SENTENCE}"


class TestADatasetTheAccountCannotReach:
    """A study that will not resolve costs the variables their names only."""

    @pytest.fixture(autouse=True)
    def _refuse_the_study(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _refuse(
            _site: str, dataset_id: str
        ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
            raise UnknownEdaDatasetError(dataset_id, [])

        monkeypatch.setattr(strategy_graph, "get_study_detail_for_dataset", _refuse)

    async def test_the_filter_is_reported_under_its_variable_id(self) -> None:
        check = await _check(_subset_spec(filtered=True))

        assert check.subset_filters == [f"{_MFS_VARIABLE} is between -4.094 and -2.0"]
        assert check.record_count == _RECORD_COUNT

    async def test_a_compute_step_still_reports_its_thresholds(self) -> None:
        check = await _check(
            _volcano_spec(filtered=True), search_name="GenesByEdaVizWithCompute"
        )

        assert check.thresholds is not None
        assert check.thresholds.significance_threshold == 0.05
        assert check.subset_filters == [f"{_MFS_VARIABLE} is between -4.094 and -2.0"]
