from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from pydantic_ai import DeferredToolRequests
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.wdk import WDKAnswer, WDKSearchConfig
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.explore.explore_agent import build_explore_agent
from pathfinder.ai.explore.readings_card import card_labels, counted_labels
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.explore_arc import FIRST_LABEL, SECOND_LABEL
from pathfinder.ai.models.mock.strategy_specs import SIGNAL_PEPTIDE
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site
from pathfinder.tests._support.record_classes import recorded_searches
from pathfinder.tests._support.recorded_columns import recorded_body
from pathfinder.tests._support.recorded_counts import recorded_count
from pathfinder.tests._support.run_context import turn_runtime

_SITE = "plasmodb"
_GENE_TYPE = "GenesByGeneType"
_GENE_TYPE_REPORT = "report_gene_type_protein_coding"
_SIGNAL_PEPTIDE_SEED = "PF3D7 Signal Peptide Genes"


def _seed_count() -> int:
    [seed] = [s for s in get_seeds_for_site(_SITE) if s.name == _SIGNAL_PEPTIDE_SEED]
    assert seed.measured is not None
    assert seed.measured.root_count is not None
    return seed.measured.root_count


def _counted(total: int) -> WDKAnswer:
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": total,
                "displayTotalCount": total,
                "viewTotalCount": total,
                "displayViewTotalCount": total,
                "responseCount": 0,
                "recordClassName": "transcript",
                "attributes": [],
                "tables": [],
                "pagination": {"offset": 0, "numRecords": 0},
            },
            "records": [],
        }
    )


@dataclass
class _Reports:
    answers: dict[str, WDKAnswer]
    ran: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        *,
        report_config: object,
        view_filters: object,
    ) -> WDKAnswer:
        del record_type, report_config, view_filters
        self.ran.append((search_name, dict(search_config.parameters)))
        return self.answers[search_name]


async def _recorded_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    return format_param_info_typed(recorded_searches()[search_name].parameters or [])


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> _Reports:
    served = _Reports(
        answers={
            SIGNAL_PEPTIDE: _counted(_seed_count()),
            _GENE_TYPE: WDKAnswer.model_validate(recorded_body(_GENE_TYPE_REPORT)),
        }
    )
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: served)
    monkeypatch.setattr(variant_comparison, "search_parameters", _recorded_parameters)
    return served


def explore_deps(
    prompt: str, session_maker: async_sessionmaker[AsyncSession]
) -> LeadDeps:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id=_SITE,
        mode="explore",
        user_prompt=prompt,
        user_message_id=uuid4(),
    )
    bind_scripted_scope(_SITE, prompt)
    return LeadDeps(
        state=state,
        intent=None,
        runtime=turn_runtime(
            site_id=_SITE, user_id=state.user_id, db_session_factory=session_maker
        ),
        retrieved_memories=[],
    )


async def test_the_explore_arc_counts_two_readings_and_offers_them(
    session_maker: async_sessionmaker[AsyncSession], reports: _Reports
) -> None:
    deps = explore_deps(
        "Which genes carry a signal peptide? [[arc:explore]]", session_maker
    )

    result = await build_explore_agent().run(
        deps.state.user_prompt, deps=deps, model=get_mock_model()
    )

    assert isinstance(result.output, DeferredToolRequests)
    [call] = result.output.approvals
    assert call.tool_name == "consult_user"
    assert card_labels(call.args_as_dict()) == [FIRST_LABEL, SECOND_LABEL]
    assert counted_labels(deps) == {
        FIRST_LABEL: _seed_count(),
        SECOND_LABEL: recorded_count(_GENE_TYPE_REPORT),
    }
    assert [name for name, _ in reports.ran] == [SIGNAL_PEPTIDE, _GENE_TYPE]
    assert deps.state.domain.named_readings == []
    assert deps.state.domain.requirements == []
    assert deps.state.domain.operational_spec is None
    assert deps.runtime.strategy_session.get_graph(None) is None


async def test_a_reply_with_no_buildable_reading_ends_with_no_card(
    session_maker: async_sessionmaker[AsyncSession], reports: _Reports
) -> None:
    deps = explore_deps(
        "What is known about this family? [[arc:explore-no-reading]]", session_maker
    )

    result = await build_explore_agent().run(
        deps.state.user_prompt, deps=deps, model=get_mock_model()
    )

    assert isinstance(result.output, str)
    assert result.output.startswith("[mock]")
    assert reports.ran == []
    assert counted_labels(deps) == {}
