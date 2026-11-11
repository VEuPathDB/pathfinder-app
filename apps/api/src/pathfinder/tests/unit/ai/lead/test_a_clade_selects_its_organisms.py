from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import WDKSearch, WDKStepTree, WDKStrategyDetails
from veupathdb_mcp.wdk import ColumnCounts, CountedValue

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind, OrganismValue
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.column_reads import ColumnSite, serve_columns
from pathfinder.tests._support.recorded_columns import column_catalog
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.step_tally_site import TallySite, ToolServer, serve
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead._site_verdict import (
    UNANSWERED_DIGEST,
    VALID,
    serve_the_site,
    verify,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

pytestmark = pytest.mark.usefixtures("collector")

_SEARCH = "GenesByOrthologPattern"
_STEP = 227352480
_STRATEGY = 214670620
_BERGHEI = "Plasmodium berghei ANKA"
_GT1 = "Toxoplasma gondii GT1"
_KNOWLESI_H = "Plasmodium knowlesi strain H"
_KNOWLESI_A1H1 = "Plasmodium knowlesi strain A1H1"
_FALCIPARUM = "Plasmodium falciparum 3D7"
_CHABAUDI = "Plasmodium chabaudi chabaudi"
_CHABAUDI_CB = "Plasmodium chabaudi chabaudi CB"
_TREU927 = "Trypanosoma brucei brucei TREU927"
_PLASMODB = suite_search("search_genes_by_ortholog_pattern")
_PORTAL_TREE: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "site_values"
        / "genus_organism.json"
    ).read_text()
)["parameter"]["vocabulary"]


def _entry(term: str, *children: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"display": term, "term": term}, "children": list(children)}


def _portal_definition() -> WDKSearch:
    [apicomplexa] = _PORTAL_TREE["children"]
    coccidia = _entry(
        "Conoidasida",
        _entry("Coccidia", _entry("Sarcocystidae", _entry("Toxoplasma", _entry(_GT1)))),
    )
    vocabulary: JsonValue = {
        **_PORTAL_TREE,
        "children": [{**apicomplexa, "children": [*apicomplexa["children"], coccidia]}],
    }
    wire = _PLASMODB.model_dump(mode="json", by_alias=True, exclude_none=True)
    wire["parameters"] = [
        {**param, "vocabulary": vocabulary} if param["name"] == "organism" else param
        for param in wire["parameters"]
    ]
    return WDKSearch.model_validate(wire)


def _deps(site_id: str, organism: str) -> LeadDeps:
    params: dict[str, ParamValue] = {"organism": MultiPickValue(values=[organism])}
    session = StrategySession(site_id=site_id)
    graph = StrategyGraph("graph-1", "Conserved", site_id)
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id="c_conserved",
            kind=StepKind.SEARCH,
            search_name=_SEARCH,
            parameters=params,
            record_class="transcript",
            display_name="Conserved",
        ),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={"c_conserved": _STEP},
        step_counts={"c_conserved": 319},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_STEP),
    )
    state = pipeline_state(site_id, user_prompt=f"genes conserved in {organism}")
    state.domain.operational_spec = OperationalSpec(
        goal="conserved genes",
        criteria=[
            Criterion(
                id="c_conserved",
                text="conserved genes",
                search_name=_SEARCH,
                record_class="transcript",
                organism_param="organism",
                resolved_params=bound(params),
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_conserved")
        ),
    )
    state.domain.requirements = []
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["c_conserved"], wdk_strategy_id=_STRATEGY
    )
    return lead_deps(state, strategy_session=session)


def _details(organism: str, total: int) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY,
            "name": "Conserved",
            "rootStepId": _STEP,
            "stepTree": {"stepId": _STEP},
            "steps": {
                str(_STEP): {
                    "id": _STEP,
                    "searchName": _SEARCH,
                    "searchConfig": {"parameters": {"organism": f'["{organism}"]'}},
                    "recordClassName": "transcript",
                    "estimatedSize": total,
                    "validation": VALID,
                }
            },
        }
    )


def _counts(*counted: tuple[str, int]) -> ColumnCounts:
    return ColumnCounts(
        step_id=_STEP,
        column="organism_full",
        display_name="Organism",
        kind="string",
        total_records=sum(count for _, count in counted),
        distinct_values=len(counted),
        values=tuple(CountedValue(value=v, count=n) for v, n in counted),
    )


async def _organism_checks(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    definition: WDKSearch,
    organism: str,
    *counted: tuple[str, int],
) -> list[SiteCheck]:
    total = sum(count for _, count in counted)
    serve_the_site(
        monkeypatch, _details(organism, total), [column_catalog()], [definition]
    )
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=total),
        ToolServer(counts=_counts(*counted)),
    )
    delta = await verify(monkeypatch, deps, UNANSWERED_DIGEST)
    return [c for c in delta.digest.review.checks if c.kind == "organism"]


async def test_a_clade_admits_every_organism_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    [check] = await _organism_checks(
        monkeypatch,
        _deps("veupathdb", "Apicomplexa"),
        _portal_definition(),
        "Apicomplexa",
        (_BERGHEI, 1760),
        (_GT1, 750),
        (_KNOWLESI_H, 430),
    )

    assert (check.status, check.evidence) == (
        "pass",
        (
            f"all 2,940 records of step {_STEP} ('Conserved') hold an organism the "
            f"strategy selects: {_BERGHEI} (1,760), {_GT1} (750), {_KNOWLESI_H} (430)"
        ),
    )


async def test_an_organism_outside_the_clade_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    [check] = await _organism_checks(
        monkeypatch,
        _deps("veupathdb", "Apicomplexa"),
        _portal_definition(),
        "Apicomplexa",
        (_BERGHEI, 1760),
        (_TREU927, 1200),
    )

    assert (check.status, check.evidence) == (
        "fail",
        (
            f"1,200 of the 2,960 records of step {_STEP} ('Conserved') hold organisms "
            f"the strategy does not select: {_TREU927} (1,200)"
        ),
    )


async def test_a_requirement_for_an_organism_under_the_clade_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps("veupathdb", "Apicomplexa")
    asked = requirement(ConstraintKind.ORGANISM, "organism", _BERGHEI).model_copy(
        update={"value": OrganismValue(organism=_BERGHEI)}
    )
    deps.state.domain.requirements = [asked]

    [check] = await _organism_checks(
        monkeypatch, deps, _portal_definition(), "Apicomplexa", (_BERGHEI, 2400)
    )

    assert (check.requirement, check.status) == (asked.id, "pass")


async def test_a_genus_admits_its_species(monkeypatch: pytest.MonkeyPatch) -> None:
    [check] = await _organism_checks(
        monkeypatch,
        _deps("plasmodb", "Plasmodium"),
        _PLASMODB,
        "Plasmodium",
        (_FALCIPARUM, 3000),
        (_KNOWLESI_A1H1, 190),
    )

    assert check.status == "pass"


async def test_a_strain_does_not_admit_its_sibling_strain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    [check] = await _organism_checks(
        monkeypatch,
        _deps("plasmodb", _KNOWLESI_H),
        _PLASMODB,
        _KNOWLESI_H,
        (_KNOWLESI_H, 4300),
        (_KNOWLESI_A1H1, 2500),
    )

    assert (check.status, check.evidence) == (
        "fail",
        (
            f"2,500 of the 6,800 records of step {_STEP} ('Conserved') hold organisms "
            f"the strategy does not select: {_KNOWLESI_A1H1} (2,500)"
        ),
    )


async def test_a_strain_does_not_admit_a_sibling_its_name_begins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    [check] = await _organism_checks(
        monkeypatch,
        _deps("plasmodb", _CHABAUDI),
        _PLASMODB,
        _CHABAUDI,
        (_CHABAUDI, 4000),
        (_CHABAUDI_CB, 3000),
    )

    assert (check.status, check.evidence) == (
        "fail",
        (
            f"3,000 of the 7,000 records of step {_STEP} ('Conserved') hold organisms "
            f"the strategy does not select: {_CHABAUDI_CB} (3,000)"
        ),
    )


async def test_a_clade_the_site_tree_does_not_expand_is_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _details("Apicomplexa", 2400), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=2400),
        ToolServer(counts=_counts((_BERGHEI, 2400))),
    )

    delta = await verify(
        monkeypatch, _deps("plasmodb", "Apicomplexa"), UNANSWERED_DIGEST
    )

    [check] = [c for c in delta.digest.review.checks if c.kind == "organism"]
    assert (
        delta.digest.success,
        check.status,
        check.why_unchecked,
        check.evidence,
    ) == (
        True,
        "unchecked",
        "no_check",
        (
            "the site's organism list could not be read, so the organisms under "
            "Apicomplexa are not known"
        ),
    )


async def test_a_leaf_selection_without_the_site_tree_fails_an_outside_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _details(_KNOWLESI_H, 6800), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=6800),
        ToolServer(counts=_counts((_KNOWLESI_H, 4300), (_KNOWLESI_A1H1, 2500))),
    )

    delta = await verify(monkeypatch, _deps("plasmodb", _KNOWLESI_H), UNANSWERED_DIGEST)

    [check] = [c for c in delta.digest.review.checks if c.kind == "organism"]
    assert (check.status, check.evidence) == (
        "fail",
        (
            f"2,500 of the 6,800 records of step {_STEP} ('Conserved') hold "
            f"organisms the strategy does not select: {_KNOWLESI_A1H1} (2,500)"
        ),
    )
