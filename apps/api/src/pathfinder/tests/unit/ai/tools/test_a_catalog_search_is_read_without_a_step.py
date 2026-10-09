"""A catalog search the strategy does not run is counted read-only, and a list
of gene ids is checked against one: giardiadb's VSP product search counts 196
genes, and of eight sampled tritrypdb genes the signal peptide search holds six."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import VocabOption
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKAnswer, WDKSearchConfig
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, SearchMatch, format_param_info_typed

from pathfinder.ai.tools.standalone.search_reads import count_search, genes_in_search
from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.domain.membership_facts import MembershipFact
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.turn_facts import SourceFact, TurnFacts
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.search_reads import SearchCount, SearchMembership
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.qa_recording import qa_recording
from pathfinder.tests._support.record_classes import (
    recorded_searches,
    serve_record_classes,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

_SUITE = Path(__file__).resolve().parents[3] / "fixtures" / "wdk"
_WB = "Giardia Assemblage A isolate WB"
_IL3000 = "Trypanosoma congolense IL3000"
_SAMPLED = [
    "TcIL3000_0_26385",
    "TcIL3000_0_50050",
    "TcIL3000_0_01550",
    "TcIL3000_0_34210",
    "TcIL3000_0_12330",
    "TcIL3000_0_17170",
    "TcIL3000_0_57830",
    "TcIL3000_0_41230",
]
_SHOWN = [
    SourceFact(url=gene_record_url("tritrypdb", g), record_id=g) for g in _SAMPLED
]
_HELD = _SAMPLED[2:]
_NOT_HELD = _SAMPLED[:2]
# The IL3000 signal peptide result holds 1,094 genes; the rest no sample named.
_SIGNAL_PEPTIDE_GENES = 1094
_OTHER_HELD = [
    f"TcIL3000_0_9{n:04d}" for n in range(_SIGNAL_PEPTIDE_GENES - len(_HELD))
]


def _recorded_report(fixture: str) -> WDKAnswer:
    recorded = RecordedWDKResponse.model_validate_json(
        qa_recording(_SUITE / f"{fixture}.json").read_text()
    )
    return WDKAnswer.model_validate(recorded.json_body())


def _gene_row(gene_id: str) -> dict[str, object]:
    return {
        "displayName": gene_id,
        "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
        "attributes": {"primary_key": gene_id},
        "tables": {},
        "tableErrors": [],
        "id": [
            {"name": "gene_source_id", "value": gene_id},
            {"name": "source_id", "value": f"{gene_id}-t26_1"},
            {"name": "project_id", "value": "TriTrypDB"},
        ],
    }


def _signal_peptide_answer(total: int) -> WDKAnswer:
    rows = [*_OTHER_HELD, *_HELD]
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": total,
                "displayTotalCount": total,
                "viewTotalCount": total,
                "displayViewTotalCount": total,
                "responseCount": len(rows),
                "recordClassName": "transcript",
                "attributes": [],
                "tables": [],
                "pagination": {"offset": 0, "numRecords": len(rows)},
            },
            "records": [_gene_row(gene) for gene in rows],
        }
    )


@dataclass
class _Reports:
    """The site's report endpoint: each search's answer, and the values it ran."""

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


def _il3000_organism(info: ParameterInfo) -> ParameterInfo:
    il3000 = VocabOption(value=_IL3000, display=_IL3000)
    return info.model_copy(update={"allowed_values": [il3000], "vocab_leaves": []})


async def _recorded_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    infos = format_param_info_typed(recorded_searches()[search_name].parameters or [])
    if search_name != "GenesWithSignalPeptide":
        return infos
    return [_il3000_organism(i) if i.name == "organism" else i for i in infos]


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> _Reports:
    served = _Reports(
        answers={
            "GenesByText": _recorded_report("report_text_vsp_quoted"),
            "GenesWithSignalPeptide": _signal_peptide_answer(_SIGNAL_PEPTIDE_GENES),
        }
    )
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: served)
    monkeypatch.setattr(variant_comparison, "search_parameters", _recorded_parameters)
    serve_record_classes(monkeypatch)
    return served


def _vsp_search() -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "VSP in product",
            "searchName": "GenesByText",
            "parameters": {
                "text_search_organism": {
                    "type": "multi-pick-vocabulary",
                    "values": [_WB],
                },
                "text_expression": {"type": "string", "value": "VSP"},
                "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
            },
        }
    )


def _signal_peptide() -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "Signal peptide",
            "searchName": "GenesWithSignalPeptide",
            "parameters": {
                "organism": {"type": "multi-pick-vocabulary", "values": [_IL3000]}
            },
        }
    )


def _tritrypdb() -> StrategySession:
    return StrategySession(site_id="tritrypdb")


async def test_a_search_the_strategy_does_not_run_is_counted_with_its_values(
    reports: _Reports,
) -> None:
    ctx = lead_run_context()

    result = await count_search(ctx, _vsp_search())

    assert returned(result, SearchCount) == SearchCount(
        label="VSP in product",
        search_name="GenesByText",
        values={
            "text_search_organism": f'["{_WB}"]',
            "text_expression": "VSP",
            "text_fields": '["product"]',
            "document_type": "gene",
        },
        gene_count=196,
    )
    assert reports.ran == [
        (
            "GenesByText",
            {
                "text_search_organism": f'["{_WB}"]',
                "text_expression": "VSP",
                "text_fields": '["product"]',
                "document_type": "gene",
            },
        )
    ]


async def test_the_count_renders_from_the_compare_reference(reports: _Reports) -> None:
    ctx = lead_run_context()

    await count_search(ctx, _vsp_search())

    comparisons = ctx.deps.state.turn_markers.comparisons
    assert comparisons == [
        ComparisonFact(
            variants=[
                ComparedVariant(
                    label="VSP in product", gene_count=196, unique_count=196
                )
            ]
        )
    ]
    facts = TurnFacts(comparisons=comparisons)
    assert render_reply("It finds [compare:VSP in product].", facts) == (
        "It finds 196 genes."
    )


async def test_a_search_the_catalog_does_not_list_names_what_the_lookup_finds(
    reports: _Reports, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[str, list[str] | None]] = []

    async def _lookup(
        _site_id: str,
        record_type: str | list[str] | None,
        query: str,
        *,
        keywords: list[str] | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[SearchMatch]:
        del record_type, category, limit
        asked.append((query, keywords))
        return [
            SearchMatch(
                name="GenesByInterproDomain",
                display_name="InterPro Domain",
                description="Find genes by InterPro domain",
                record_type="transcript",
            )
        ]

    monkeypatch.setattr(catalog, "search_for_searches", _lookup)
    domain = VariantInput(
        label="Protein domain", search_name="GenesByProteinDomain", parameters={}
    )

    with pytest.raises(ModelRetry) as refused:
        await count_search(lead_run_context(), domain)

    assert asked == [("Genes By Protein Domain", ["GenesByProteinDomain"])]
    assert str(refused.value) == (
        "plasmodb lists no search GenesByProteinDomain (Protein domain). The "
        "catalog lookup for 'Genes By Protein Domain' finds: GenesByInterproDomain "
        "(InterPro Domain). Call again with one of these names. A search is "
        "absent from plasmodb only when this lookup finds none."
    )
    assert reports.ran == []


async def test_an_unlisted_name_marks_the_turn_as_looked_up(
    reports: _Reports, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=[]))
    ctx = lead_run_context()
    domain = VariantInput(
        label="Protein domain", search_name="GenesByProteinDomain", parameters={}
    )

    with pytest.raises(ModelRetry):
        await count_search(ctx, domain)

    assert ctx.deps.state.turn_markers.catalog_looked_up is True
    assert reports.ran == []


async def test_the_signal_peptide_search_holds_six_of_the_eight_sampled_genes(
    reports: _Reports,
) -> None:
    ctx = lead_run_context(site_id="tritrypdb", strategy_session=_tritrypdb())

    result = await genes_in_search(ctx, _signal_peptide(), _SAMPLED)

    assert returned(result, SearchMembership) == SearchMembership(
        label="Signal peptide",
        search_name="GenesWithSignalPeptide",
        values={"organism": f'["{_IL3000}"]', "signalp_version": "SignalP-6.0"},
        gene_count=1094,
        held=_HELD,
        not_held=_NOT_HELD,
        unread=[],
    )


async def test_the_genes_default_to_the_records_the_conversation_showed(
    reports: _Reports,
) -> None:
    ctx = lead_run_context(site_id="tritrypdb", strategy_session=_tritrypdb())
    ctx.deps.state.domain.record_shown(_SHOWN)

    result = await genes_in_search(ctx, _signal_peptide())

    membership = returned(result, SearchMembership)
    assert (membership.held, membership.not_held) == (_HELD, _NOT_HELD)


async def test_no_gene_ids_and_no_shown_record_is_refused(reports: _Reports) -> None:
    ctx = lead_run_context(site_id="tritrypdb", strategy_session=_tritrypdb())

    with pytest.raises(ModelRetry) as refused:
        await genes_in_search(ctx, _signal_peptide())

    assert str(refused.value) == (
        "No gene ids were given, and this conversation has shown no record. "
        "Name the gene ids to check."
    )
    assert reports.ran == []


async def test_a_membership_renders_by_record_and_by_shared_count(
    reports: _Reports,
) -> None:
    ctx = lead_run_context(site_id="tritrypdb", strategy_session=_tritrypdb())

    await genes_in_search(ctx, _signal_peptide(), _SAMPLED)

    markers = ctx.deps.state.turn_markers
    assert markers.memberships == [
        MembershipFact(
            search_label="Signal peptide",
            records=[
                ListedRecord(record_id=g, url=gene_record_url("tritrypdb", g))
                for g in _SAMPLED
            ],
            held=_HELD,
        )
    ]
    assert markers.comparisons == [
        ComparisonFact(
            variants=[
                ComparedVariant(label="asked genes", gene_count=8, unique_count=2),
                ComparedVariant(
                    label="Signal peptide", gene_count=1094, unique_count=1088
                ),
            ],
            overlaps=[SharedGenes(a="asked genes", b="Signal peptide", shared=6)],
        )
    ]
    facts = TurnFacts(memberships=markers.memberships, comparisons=markers.comparisons)
    reply = (
        "Of [compare:asked genes], [compare:asked genes,Signal peptide:shared] "
        "hold a signal peptide; [record:TcIL3000_0_26385] does not."
    )
    url = gene_record_url("tritrypdb", "TcIL3000_0_26385")
    assert render_reply(reply, facts) == (
        "Of 8 genes, 6 genes hold a signal peptide; "
        f"[TcIL3000_0_26385]({url}) does not."
    )
    assert facts.record_ids() == _SAMPLED


async def test_ids_past_the_capped_read_are_unread_not_absent(
    reports: _Reports,
) -> None:
    reports.answers["GenesWithSignalPeptide"] = _signal_peptide_answer(60_000)
    ctx = lead_run_context(site_id="tritrypdb", strategy_session=_tritrypdb())

    result = await genes_in_search(ctx, _signal_peptide(), _SAMPLED)

    membership = returned(result, SearchMembership)
    assert (membership.held, membership.not_held, membership.unread) == (
        _HELD,
        [],
        _NOT_HELD,
    )


def test_a_facts_part_that_shows_no_record_keeps_the_earlier_records() -> None:
    ctx = lead_run_context()
    domain = ctx.deps.state.domain

    domain.record_shown(_SHOWN)
    domain.record_shown([])

    assert domain.shown_records == _SHOWN
