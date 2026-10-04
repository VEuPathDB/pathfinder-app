"""An entity id the open study does not declare is a refusal that names the
entities it does declare."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import walk_entities

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.eda import authoring
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    phenotype_study,
    read_analysis_detail,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def test_a_mistyped_entity_is_refused_with_the_entities_the_study_declares(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A mistyped entity id is a refusal the model can correct, never a crash."""
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "read_analysis", read_analysis_detail)
    monkeypatch.setattr(authoring, "get_study_detail_for_dataset", phenotype_study)
    _entry, study = await phenotype_study("plasmodb", PHENOTYPE_DATASET)
    declared = ", ".join(
        f"{e.id} ({e.display_name})" for e in walk_entities(study.root_entity)
    )

    with pytest.raises(ModelRetry) as refused:
        await eda_analysis.preview_eda_subset(lead_ctx, entity_id="GENE_PHENOTYPE")

    assert str(refused.value) == (
        f"Study {study.id} has no entity GENE_PHENOTYPE. Its entities are: "
        f"{declared}. Call preview_eda_subset again with one of them."
    )
