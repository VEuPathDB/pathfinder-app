from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from strategist.ai.explore.explore_agent import build_explore_agent
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.tools.standalone._eda_guidance import (
    SHEET_GUIDANCE,
    no_gene_subset_sentence,
)
from strategist.domain.eda_parts import (
    EdaComparison,
    EdaFilterSheetEntry,
    OpenEdaSheet,
)
from strategist.jobs.impls.eda_compute_impl import compute_result
from strategist.services.eda.authoring import SubsetPreview
from strategist.services.eda.compute import RetainedSummary
from strategist.services.eda.gene_subset import GeneSubset
from strategist.tests._support.eda_wire import PHENOTYPE_DATASET, PHENOTYPE_ENTITY
from strategist.tests._support.run_context import lead_run_context
from strategist.tests._support.tool_names import foreign_names

_SHEET = OpenEdaSheet(
    dataset_id=PHENOTYPE_DATASET,
    entries=[
        EdaFilterSheetEntry(
            entity_id=PHENOTYPE_ENTITY,
            variable_id="VAR_parasitemia",
            display_name="Parasitemia",
            filter_type="stringSet",
            vocabulary=["high", "low"],
            vocabulary_total=2,
        )
    ],
)


async def test_explore_is_pinned_the_open_eda_sheet() -> None:
    deps = lead_run_context(user_prompt="which samples had high parasitemia?").deps
    deps.state.domain.pin_eda_sheet(_SHEET)
    seen: list[AgentInfo] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.append(info)
        return ModelResponse(parts=[TextPart("High parasitemia is one value.")])

    agent = build_explore_agent()
    with agent.override(model=FunctionModel(answer)):
        await agent.run(deps.state.user_prompt, deps=deps)

    [info] = seen
    assert "# Open EDA filter sheet" in (info.instructions or "")
    assert "VAR_parasitemia" in (info.instructions or "")


def test_the_sheet_guidance_names_only_what_explore_holds() -> None:
    assert foreign_names(SHEET_GUIDANCE, build_explore_agent()) == []
    assert foreign_names(SHEET_GUIDANCE, build_lead_agent()) == []


def test_a_subset_without_a_gene_filter_names_no_export_tool() -> None:
    samples = SubsetPreview(
        entity_id="EUPATH_0000609",
        entity_display_name="Sample",
        entity_display_name_plural="Samples",
        count=6,
        unfiltered_count=12,
        distribution=None,
    )
    subset = GeneSubset(
        gene_entity_id="ENT_fd574cd6",
        gene_problem=None,
        gene_entity_name="pfal3D7 htseq counts",
        filtered_entity_names=("Sample",),
        num_filters=1,
        filters_genes=False,
    )

    sentence = no_gene_subset_sentence(samples, subset=subset)

    assert foreign_names(sentence, build_explore_agent()) == []
    assert "6 of 12 Samples selected" in sentence


def test_a_compute_result_names_no_export_tool() -> None:
    guidance = compute_result(
        job_id="job-1",
        status="complete",
        method="DESeq",
        effect_size_label="log2(Fold Change)",
        summary=RetainedSummary(
            total_rows=201,
            unparseable_rows=1,
            retained=67,
            retained_up=33,
            retained_down=34,
        ),
        comparison=EdaComparison(group_a=["24h pbm"], group_b=["18h pbm"]),
    ).guidance

    assert foreign_names(guidance, build_explore_agent()) == []
    assert "upOnly keeps the 33, downOnly the 34." in guidance
