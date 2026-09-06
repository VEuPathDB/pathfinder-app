"""Recorded EDA studies, analysis documents and the run context a tool sees."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.eda_study import walk_entities
from veupathdb.domain.strategy.session import StrategySession
from veupathdb.eda.models import (
    EdaAnalysisDetail,
    EdaFilter,
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaStudyDetailResponse,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.eda_parts import EdaEntityCount
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
    fixture,
)

ANALYSIS_ID = "t4fszEJ"
SPECIES_VARIABLE = "VAR_035294d0"


def no_database() -> AsyncSession:
    """The factory a tool that must not touch the database is given."""
    msg = "db factory should not be called in these tests"
    raise AssertionError(msg)


def lead_run_context(
    *,
    prompt: str,
    conversation_id: UUID | None = None,
    session: StrategySession | None = None,
) -> RunContext[LeadDeps]:
    """The context a Lead-mounted tool runs under, with no database behind it."""
    state = PipelineState(
        conversation_id=conversation_id or uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=prompt,
    )
    runtime = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=session or StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )
    deps = LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage(), messages=[])


def permission_entry(*, results_all: bool = True) -> EdaPermissionEntry:
    """The account's permission on the phenotype study."""
    return EdaPermissionEntry.model_validate(
        {
            "studyId": PHENOTYPE_STUDY,
            "displayName": "Rodent malaria phenotypes",
            "actionAuthorization": {
                "studyMetadata": True,
                "subsetting": True,
                "resultsAll": results_all,
            },
        }
    )


async def phenotype_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    """The recorded phenotype study, as the catalog resolves a dataset id."""
    detail = EdaStudyDetailResponse.model_validate(
        fixture("study_detail_phenotype")
    ).study
    return permission_entry(), detail


def study_of(variables: list[dict[str, Any]], *, entity_id: str) -> EdaStudyDetail:
    """A one-entity study holding exactly the variables a case needs."""
    return EdaStudyDetail.model_validate(
        {
            "id": PHENOTYPE_STUDY,
            "rootEntity": {
                "id": entity_id,
                "displayName": entity_id,
                "displayNamePlural": entity_id,
                "variables": variables,
            },
        }
    )


def analysis_detail() -> EdaAnalysisDetail:
    """The open analysis, holding one species filter and no computation."""
    return EdaAnalysisDetail.model_validate(
        {
            "analysisId": ANALYSIS_ID,
            "displayName": "berghei subset",
            "studyId": PHENOTYPE_DATASET,
            "numFilters": 1,
            "numComputations": 0,
            "descriptor": {
                "subset": {
                    "descriptor": [
                        {
                            "entityId": PHENOTYPE_ENTITY,
                            "variableId": SPECIES_VARIABLE,
                            "type": "stringSet",
                            "stringSet": ["P. berghei"],
                        }
                    ],
                    "uiSettings": {},
                },
                "computations": [],
                "starredVariables": [],
                "dataTableConfig": {},
                "derivedVariables": [],
            },
        }
    )


async def read_analysis_detail(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
    """The analysis read every render performs, answered from the double."""
    del analysis_id
    return analysis_detail()


class RevisionCounter:
    """A counting stand-in for the binding's atomic revision bump."""

    def __init__(self) -> None:
        self.count = 0

    async def bump(self, *, conversation_id: object) -> int:
        del conversation_id
        self.count += 1
        return self.count


async def recorded_entity_counts(
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


async def no_gene_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    """A study with no gene id variable, so nothing can be exported from it."""
    sample = {
        "id": "VAR_sample",
        "type": "string",
        "displayName": "Sample",
        "dataShape": "categorical",
        "vocabulary": ["a", "b"],
    }
    return permission_entry(results_all=False), study_of([sample], entity_id="E")
