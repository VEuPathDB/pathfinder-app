"""The chunks the EDA tools put on their returns, and when the card repeats."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain import walk_entities
from veupathdb.eda import (
    EdaDistributionResponse,
    EdaFilter,
    EdaStudyDetail,
)

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.tools.standalone.eda_stream_parts import (
    analysis_state_chunks_if_changed,
    eda_analysis_state_chunk,
    eda_subset_preview_chunk,
    eda_viz_chunk,
)
from pathfinder.domain.eda_parts import (
    EdaAnalysisState,
    EdaComparison,
    EdaEntityCount,
    EdaVolcanoPoint,
)
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.services.eda.compute import RetainedSummary
from pathfinder.services.eda.description import permission_facts
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    analysis_detail,
    phenotype_study,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    fixture,
)


async def _entity_counts(
    _site: str, *, study: EdaStudyDetail, filters: Sequence[EdaFilter]
) -> list[EdaEntityCount]:
    """The recorded phenotype pair, for every entity the study declares."""
    del filters
    return [
        EdaEntityCount(
            entity_id=entity.id,
            entity_display_name=entity.display_name,
            count=4011,
            unfiltered_count=4279,
        )
        for entity in walk_entities(study.root_entity)
    ]


def _counts(count: int) -> list[EdaEntityCount]:
    return [
        EdaEntityCount(
            entity_id="GENE_PHENOTYPE_DATA_ENTITY",
            entity_display_name="Gene",
            count=count,
            unfiltered_count=5000,
        )
    ]


def _state(
    *,
    num_computations: int = 0,
    entity_counts: list[EdaEntityCount] | None = None,
) -> EdaAnalysisState:
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id="DS_1",
        study_id="STUDY_1",
        analysis_id="AN_1",
        revision=None,
        study_display_name="Febrile versus normal heat-shock expression",
        display_name="Heat shock",
        num_filters=0,
        num_computations=num_computations,
        filters=[],
        filter_summaries=[],
        entity_counts=entity_counts if entity_counts is not None else [],
        can_export_rows=True,
    )


def _pipeline() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


def test_an_unchanged_state_emits_no_second_card() -> None:
    pipeline = _pipeline()
    first = analysis_state_chunks_if_changed(_state(), domain=pipeline.domain)
    second = analysis_state_chunks_if_changed(_state(), domain=pipeline.domain)
    assert len(first) == 1
    assert second == []


def test_a_changed_state_emits_again() -> None:
    pipeline = _pipeline()
    analysis_state_chunks_if_changed(_state(), domain=pipeline.domain)
    changed = analysis_state_chunks_if_changed(
        _state(num_computations=1), domain=pipeline.domain
    )
    assert len(changed) == 1


def test_the_card_reconciles_by_its_analysis_id() -> None:
    pipeline = _pipeline()
    (chunk,) = analysis_state_chunks_if_changed(_state(), domain=pipeline.domain)
    assert chunk.id == "AN_1"


def test_a_changed_subset_count_emits_again() -> None:
    """The counts are part of the state the card shows, so they re-emit it."""
    pipeline = _pipeline()
    analysis_state_chunks_if_changed(
        _state(entity_counts=_counts(120)), domain=pipeline.domain
    )
    changed = analysis_state_chunks_if_changed(
        _state(entity_counts=_counts(96)), domain=pipeline.domain
    )

    assert len(changed) == 1
    facts = pipeline.domain.eda_analysis
    assert facts is not None
    assert [c.count for c in facts.entity_counts] == [96]


def _preview(
    *,
    count: int,
    distribution: EdaDistributionResponse | None,
    note: str | None = None,
) -> SubsetPreview:
    return SubsetPreview(
        entity_id=PHENOTYPE_ENTITY,
        entity_display_name="Gene phenotype",
        count=count,
        unfiltered_count=4279,
        distribution=distribution,
        distribution_note=note,
    )


def _subset_chunk(preview: SubsetPreview, **kwargs: Any) -> DataChunk:
    return eda_subset_preview_chunk(
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        preview=preview,
        variable_id=kwargs.pop("variable_id", None),
        variable_display_name=kwargs.pop("variable_display_name", ""),
        is_multi_valued=kwargs.pop("is_multi_valued", False),
        **kwargs,
    )


def _categorical() -> EdaDistributionResponse:
    return EdaDistributionResponse.model_validate(fixture("distribution_categorical"))


def test_the_subset_preview_chunk_converts_a_histogram_to_a_series() -> None:
    chunk = _subset_chunk(
        _preview(count=4011, distribution=_categorical()),
        variable_id=SPECIES_VARIABLE,
        variable_display_name="Species",
        is_multi_valued=True,
    )
    assert chunk.type == "data-eda.subset-preview"
    counts = chunk.data["entityCounts"]
    assert counts[0]["count"] == 4011
    assert counts[0]["unfilteredCount"] == 4279
    assert counts[0]["entityDisplayName"] == "Gene phenotype"
    series = chunk.data["distribution"]
    assert series["labels"] == ["P. berghei", "P. falciparum", "P. yoelii"]
    assert series["values"] == [4011.0, 4130.0, 268.0]
    assert series["isMultiValued"] is True
    assert series["numVarValues"] == 8409
    assert series["subsetSize"] == 4279


def test_the_subset_preview_chunk_carries_the_caption_the_model_wrote() -> None:
    chunk = _subset_chunk(
        _preview(count=4011, distribution=None),
        caption="Species of the 4,011 phenotyped genes the filters keep",
    )
    assert chunk.data["caption"] == (
        "Species of the 4,011 phenotyped genes the filters keep"
    )


def test_the_subset_preview_chunk_leaves_the_caption_empty_when_unset() -> None:
    chunk = _subset_chunk(_preview(count=4011, distribution=None))
    assert chunk.data["caption"] == ""


def test_the_subset_preview_chunk_omits_the_series_when_there_is_none() -> None:
    note = "Variable VAR_x is continuous and declares no binWidth."
    chunk = _subset_chunk(_preview(count=4011, distribution=None, note=note))
    assert chunk.data["distribution"] is None
    assert chunk.data["distributionNote"] == note


def _point(index: int, *, retained: bool) -> EdaVolcanoPoint:
    return EdaVolcanoPoint(
        point_id=f"PF3D7_{index:07d}",
        effect_size=2.0 if retained else 0.1,
        p_value=0.001,
        adjusted_p_value=0.01,
        retained=retained,
    )


def _viz_chunk(
    *,
    summary: RetainedSummary,
    points: list[EdaVolcanoPoint],
    effect_direction: str = "upAndDown",
    caption: str | None = None,
    comparison: EdaComparison | None = None,
) -> DataChunk:
    extra = {} if caption is None else {"caption": caption}
    return eda_viz_chunk(
        dataset_id="DS_e973eadd57",
        analysis_id=ANALYSIS_ID,
        effect_size_label="log2(Fold Change)",
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction=effect_direction,
        summary=summary,
        points=points,
        comparison=comparison or EdaComparison(group_a=["normal"], group_b=["febrile"]),
        **extra,
    )


def _summary(**kwargs: int) -> RetainedSummary:
    fields = {
        "total_rows": 1,
        "unparseable_rows": 0,
        "retained": 0,
        "retained_up": 0,
        "retained_down": 0,
    }
    fields.update(kwargs)
    return RetainedSummary(**fields)


def test_the_viz_chunk_reports_the_measured_totals() -> None:
    chunk = _viz_chunk(
        summary=_summary(
            total_rows=5511,
            unparseable_rows=1,
            retained=1543,
            retained_up=800,
            retained_down=743,
        ),
        points=[_point(1, retained=True)],
    )
    assert chunk.type == "data-eda.viz"
    assert chunk.data["chart"] == "volcano"
    assert chunk.data["totalPoints"] == 5511
    assert chunk.data["retainedPoints"] == 1543
    assert chunk.data["effectDirection"] == "upAndDown"


def test_the_viz_chunk_carries_the_caption_the_model_wrote() -> None:
    chunk = _viz_chunk(
        summary=_summary(total_rows=5511, retained=1543, retained_up=800),
        points=[_point(1, retained=True)],
        caption="Genes higher in febrile samples than in normal samples",
    )
    assert chunk.data["caption"] == (
        "Genes higher in febrile samples than in normal samples"
    )


def test_the_viz_chunk_leaves_the_caption_empty_when_unset() -> None:
    chunk = _viz_chunk(summary=_summary(), points=[])
    assert chunk.data["caption"] == ""


def test_the_viz_chunk_names_the_labels_of_both_groups() -> None:
    chunk = _viz_chunk(
        summary=_summary(),
        points=[],
        comparison=EdaComparison(group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"]),
    )
    assert chunk.data["comparison"] == {
        "groupA": ["24h pbm"],
        "groupB": ["18h pbm", "36h pbm"],
    }


def test_the_viz_chunk_refuses_a_direction_no_chart_draws() -> None:
    with pytest.raises(ValidationError):
        _viz_chunk(summary=_summary(), points=[], effect_direction="sideways")


def test_the_viz_chunk_caps_the_points_and_keeps_every_retained_one() -> None:
    """The cap is below the measured 5511 rows, so the order decides who survives."""
    points = [_point(i, retained=False) for i in range(4500)]
    points.extend(_point(9000 + i, retained=True) for i in range(20))
    chunk = _viz_chunk(
        summary=_summary(total_rows=4520, retained=20, retained_up=20),
        points=points,
    )
    sent = chunk.data["points"]
    assert len(sent) == 4000
    assert sum(1 for point in sent if point["retained"]) == 20


async def test_the_analysis_state_chunk_names_the_part_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binding, "subset_entity_counts", _entity_counts)
    entry, study = await phenotype_study("plasmodb", PHENOTYPE_DATASET)
    chunk = eda_analysis_state_chunk(
        await binding.analysis_state(
            site_id="plasmodb",
            dataset_id=PHENOTYPE_DATASET,
            entry=permission_facts(entry),
            study=study,
            analysis=analysis_detail(),
            revision=3,
        )
    )
    assert chunk.type == "data-eda.analysis-state"
    assert chunk.data["analysisId"] == ANALYSIS_ID
    assert chunk.data["analysisUrl"] == (
        f"https://plasmodb.org/plasmo/app/workspace/analyses/"
        f"{PHENOTYPE_DATASET}/{ANALYSIS_ID}"
    )
    assert chunk.data["numFilters"] == 1
    assert chunk.data["revision"] == 3
    assert chunk.data["filterSummaries"] == ["Species is one of P. berghei"]
    assert chunk.data["entityCounts"] == [
        {
            "entityId": PHENOTYPE_ENTITY,
            "entityDisplayName": "Gene Phenotype Data",
            "count": 4011,
            "unfilteredCount": 4279,
        }
    ]
    assert chunk.data["filters"] == [
        {
            "entityId": PHENOTYPE_ENTITY,
            "variableId": SPECIES_VARIABLE,
            "type": "stringSet",
            "stringSet": ["P. berghei"],
        }
    ]
