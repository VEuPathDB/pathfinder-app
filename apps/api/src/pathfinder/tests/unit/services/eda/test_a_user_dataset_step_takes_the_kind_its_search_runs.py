"""An unstamped user-dataset step takes the kind its search runs, read from the
site's recorded definition, whatever computation its document carries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda import analysis_kinds
from pathfinder.services.eda.analysis_kinds import analysis_kinds_of
from pathfinder.services.eda.export import exported_analysis
from pathfinder.tests._support.eda_step_doubles import DE_DATASET
from pathfinder.tests.unit.ai.lead._analysis_thread import document

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "wdk"
_DESEQ = "GenesByDESeqUserDataset"
_PHENOTYPE = "GenesByPhenotypeUserDataset"


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.loads((_FIXTURES / "user_dataset_searches_plasmodb.json").read_text())
    by_name = {e["urlSegment"]: WDKSearch.model_validate(e) for e in raw}

    async def record_type(_site: str, _name: str, _record: str | None) -> str:
        return "transcript"

    async def definition(_site: str, _record: str, name: str) -> WDKSearch:
        return by_name[name]

    monkeypatch.setattr(analysis_kinds, "resolve_search_record_type", record_type)
    monkeypatch.setattr(analysis_kinds, "read_search_definition", definition)


def _node(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=DE_DATASET),
            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
        },
    )


@pytest.mark.usefixtures("recorded")
async def test_the_deseq_search_is_a_compute_and_the_phenotype_search_a_subset() -> (
    None
):
    kinds = await analysis_kinds_of(
        site_id="plasmodb",
        record_type="transcript",
        nodes=[_node("step_deseq", _DESEQ), _node("step_phenotype", _PHENOTYPE)],
    )

    assert kinds == {
        "step_deseq": StampedKind(search_name=_DESEQ, kind=AnalysisKind.COMPUTE),
        "step_phenotype": StampedKind(search_name=_PHENOTYPE, kind=AnalysisKind.SUBSET),
    }


@pytest.mark.usefixtures("recorded")
async def test_an_unstamped_deseq_user_dataset_step_reads_its_cut() -> None:
    node = _node("step_deseq", _DESEQ)
    kinds = await analysis_kinds_of(
        site_id="plasmodb", record_type="transcript", nodes=[node]
    )

    binding = exported_analysis(kinds[node.id].kind, node.parameters)

    assert binding is not None
    assert (
        binding.effect_size_threshold,
        binding.significance_threshold,
        binding.effect_direction,
    ) == (1.0, 0.05, "upOnly")
