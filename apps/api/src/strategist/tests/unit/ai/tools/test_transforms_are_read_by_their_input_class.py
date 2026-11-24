from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKRecordType, WDKSearch

from strategist.ai.agents.frame_answer import hold_the_frame_answer
from strategist.ai.agents.frame_result_checks import hold_an_absence_to_a_read
from strategist.ai.agents.state import AgentToolState, CatalogRead
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.tools.standalone._frame_roles import role_problems
from strategist.ai.tools.standalone.catalog import list_transforms
from strategist.ai.tools.toolsets.frame import _frame_enum_overrides
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from strategist.services.strategies import record_classes
from strategist.tests._support.held_answers import let_through
from strategist.tests._support.orthomcl_record_classes import GROUP, SEQUENCE
from strategist.tests._support.orthomcl_site import BY_ID_LIST, GROUPS_FROM_SEQUENCES
from strategist.tests._support.recorded_searches import client_search
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.lead.conftest import requirement

from .conftest import agent_run_context

_RECORDED = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "sibling_strain_list_transforms.json"
    ).read_text()
)
_PLAN_CLASS: str = _RECORDED["planRecordClass"]
_FROM_TRANSCRIPTS = _RECORDED["listTransforms"]["output"][0]

_TRANSCRIPT = WDKRecordType(
    url_segment="transcript",
    display_name="Gene",
    display_name_plural="Genes",
    short_display_name="Gene",
)
_GENE = WDKRecordType(
    url_segment="gene",
    display_name="Gene",
    display_name_plural="Genes",
    short_display_name="Gene",
)
_GENES_FROM_TRANSCRIPTS = WDKSearch(
    url_segment=_FROM_TRANSCRIPTS["name"],
    display_name=_FROM_TRANSCRIPTS["displayName"],
    description=_FROM_TRANSCRIPTS["description"],
    output_record_class_name="gene",
    allowed_primary_input_record_class_names=[_PLAN_CLASS],
)


class _Discovery:
    def __init__(
        self, record_types: Sequence[WDKRecordType], searches: Sequence[WDKSearch]
    ) -> None:
        self._record_types = list(record_types)
        self._searches = list(searches)

    async def get_record_types(self, _site_id: str) -> list[WDKRecordType]:
        return self._record_types

    async def get_searches(self, _site_id: str, record_type: str) -> list[WDKSearch]:
        return [s for s in self._searches if s.output_record_class_name == record_type]


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    record_types: Sequence[WDKRecordType],
    searches: Sequence[WDKSearch],
) -> None:
    discovery = _Discovery(record_types, searches)
    monkeypatch.setattr(
        "veupathdb_mcp.catalog.searches.get_discovery_service", lambda: discovery
    )
    monkeypatch.setattr(
        record_classes, "get_raw_record_types", discovery.get_record_types
    )
    monkeypatch.setattr(record_classes, "get_raw_searches", discovery.get_searches)


def _serve_toxodb(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        [_TRANSCRIPT, _GENE],
        [
            client_search("search_genes_by_orthologs"),
            client_search("search_boolean_transcript"),
            client_search("search_genes_by_ortholog_pattern"),
            _GENES_FROM_TRANSCRIPTS,
        ],
    )


def _planned(*classes: str) -> AgentToolState:
    return AgentToolState(
        operational_spec_draft=OperationalSpec(
            criteria=[
                Criterion(id=f"c_{k}", text=f"step {k}", record_class=record_class)
                for k, record_class in enumerate(classes)
            ]
        )
    )


async def _listed(state: AgentToolState, site_id: str) -> list[tuple[str, str]]:
    rows = returned(
        await list_transforms(agent_run_context(site_id=site_id, agent_state=state)),
        list[dict[str, str]],
    )
    return [(row["name"], row["recordType"]) for row in rows]


async def test_a_transcript_plan_reads_the_ortholog_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_toxodb(monkeypatch)

    listed = await _listed(_planned(_PLAN_CLASS), "toxodb")

    assert listed == [
        ("GenesByOrthologs", "transcript"),
        ("GenesFromTranscripts", "gene"),
    ]


async def test_a_protein_plan_reads_the_transform_listed_under_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, [SEQUENCE, GROUP], [BY_ID_LIST, GROUPS_FROM_SEQUENCES])

    listed = await _listed(_planned("sequence"), "orthomcl")

    assert listed == [("GroupsFromSequences", "group")]


async def test_a_role_refusal_names_the_transforms_the_listing_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_toxodb(monkeypatch)
    state = _planned(_PLAN_CLASS)
    ctx = agent_run_context(site_id="toxodb", agent_state=state)

    refused = await role_problems(
        ctx, client_search("search_genes_by_ortholog_pattern"), "transform"
    )

    assert [p.sentence for p in refused.found] == [
        (
            "GenesByOrthologPattern takes no input step, so it cannot be a "
            'transform. Bind it with role="filter" or role="seed", or name one of '
            "the transforms that take transcript: GenesByOrthologs, "
            "GenesFromTranscripts."
        )
    ]


def _absent_r3() -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        notes="No orthology transform is available on this site.",
        requirement_problems=[
            RequirementReport(
                requirement="R3", problem=RequirementProblem.SITE_HAS_NO_SEARCH
            )
        ],
    )


def _stating_three(state: AgentToolState) -> AgentToolState:
    state.stated_requirements = [
        requirement(ConstraintKind.PROPERTY, "Pfam kinase", "Pfam kinase domain"),
        requirement(ConstraintKind.ORGANISM, "GT1", "Toxoplasma gondii GT1"),
        requirement(ConstraintKind.PROPERTY, "expression", "bradyzoite expression"),
    ]
    return state


def _transforms_read(classes: frozenset[str]) -> CatalogRead:
    return CatalogRead(
        tool_call_id="call_11",
        tool="list_transforms",
        record_type="",
        accepting=classes,
        hits=[],
    )


async def test_an_absence_no_read_of_the_plan_covers_is_sent_back() -> None:
    state = _stating_three(_planned(_PLAN_CLASS))
    state.catalog_reads = [_transforms_read(frozenset({"gene"}))]

    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_frame_answer(agent_run_context(agent_state=state), _absent_r3())

    assert (
        "site_has_no_search for R3 rests on no catalog read of transcript this pass"
        in str(sent_back.value)
    )


async def test_an_absence_a_read_of_the_plan_covers_stands() -> None:
    state = _stating_three(_planned(_PLAN_CLASS))
    state.catalog_reads = [_transforms_read(frozenset({_PLAN_CLASS}))]

    answered = await hold_the_frame_answer(
        agent_run_context(agent_state=state), _absent_r3()
    )

    assert isinstance(answered, FrameResult)
    assert [r.requirement for r in answered.requirement_problems] == ["R3"]


def test_an_absence_left_unread_reaches_the_lead_as_not_read() -> None:
    state = _stating_three(_planned(_PLAN_CLASS))
    output = _absent_r3()

    final = let_through(
        hold_an_absence_to_a_read(agent_run_context(agent_state=state), output),
        output,
    )

    assert final.requirement_problems == []
    assert [(g.kind, g.sentence) for g in final.gaps] == [
        (
            "absence_not_read",
            (
                "The pass reported R3 as a search the site lacks, and no catalog "
                "read of this pass covers transcript, so it was not read. "
                "list_transforms or search_for_searches on transcript answers it."
            ),
        )
    ]


async def test_the_listing_is_recorded_as_a_read_of_the_plans_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_toxodb(monkeypatch)
    state = _planned(_PLAN_CLASS)

    await _listed(state, "toxodb")

    [read] = state.catalog_reads
    assert (read.tool, read.accepting) == ("list_transforms", frozenset({_PLAN_CLASS}))
    assert [(h.name, h.record_type) for h in read.hits] == [
        ("GenesByOrthologs", "transcript"),
        ("GenesFromTranscripts", "gene"),
    ]


async def test_a_listed_transform_passes_the_search_name_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_toxodb(monkeypatch)
    state = _planned(_PLAN_CLASS)

    await _listed(state, "toxodb")

    overrides = _frame_enum_overrides(agent_run_context(agent_state=state))
    assert "GenesByOrthologs" in overrides[("set_criterion", "search_name")]
