"""The organism-universe arc binds the site organism alone as a criterion beside
the signal peptide criterion, and the real ``set_structure`` drops it."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import SheetEntry, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import proposal_args
from pathfinder.ai.models.mock.strategy_specs import TM_DOMAINS, tm_domains
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode
from pathfinder.tests._support.organism_reads import serve_organism_reads
from pathfinder.tests._support.recorded_searches import client_search, suite_search
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.models import _mock_turns
from pathfinder.tests.unit.ai.models._mock_turns import args_of, play
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

PEST = "Anopheles gambiae PEST"
_MESSAGE = (
    f"Find {PEST} genes whose proteins have a predicted signal peptide. "
    "[[arc:organism-universe]]"
)


@pytest.fixture(autouse=True)
def _gene_model_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sheet vectorbase publishes for the gene model search."""
    monkeypatch.setitem(
        _mock_turns.SHEET_PARAMS,
        "GenesByGeneModelChars",
        ["organism_select_none", "gene_or_transcript", "gene_model_char"],
    )


def _marked(search_name: str) -> str | None:
    """The parameter the recorded definition of the search marks as its organism."""
    definition = (
        client_search("search_genes_by_gene_model_chars")
        if search_name == "GenesByGeneModelChars"
        else suite_search("search_genes_with_signal_peptide")
    )
    infos = format_param_info_typed(definition.parameters or [])
    return next((i.name for i in infos if i.organism_param), None)


def _bound(call: dict[str, object]) -> Criterion:
    """The criterion one binding call of the arc records."""
    params = call["params"]
    assert isinstance(params, dict)
    search_name = str(call["search_name"])
    return Criterion(
        id=str(call["criterion_id"]),
        text=str(call["text"]),
        search_name=search_name,
        organism_param=_marked(search_name),
        resolved_params={
            name: MultiPickValue(values=value)
            for name, value in params.items()
            if isinstance(value, list)
        },
        defaulted_params=sorted(n for n, v in params.items() if v is None),
    )


def _bindings(calls: list[ToolCallPart]) -> list[dict[str, object]]:
    return [a for a in args_of(calls, "set_criterion") if "params" in a]


def test_the_arc_binds_the_organism_alone_beside_the_signal_peptide() -> None:
    calls = play("frame", "vectorbase", _MESSAGE)

    assert next((a["criterion_id"], a["params"]) for a in _bindings(calls)) == (
        "organism_genes",
        {
            "organism_select_none": [PEST],
            "gene_or_transcript": None,
            "gene_model_char": None,
        },
    )
    assert args_of(calls, "set_structure")[0]["root"] == {
        "kind": "combine",
        "criterionId": None,
        "operator": "INTERSECT",
        "inputs": [
            {
                "kind": "leaf",
                "criterionId": "organism_genes",
                "operator": None,
                "inputs": [],
            },
            {
                "kind": "leaf",
                "criterionId": "signal_peptide",
                "operator": None,
                "inputs": [],
            },
        ],
    }


async def test_the_real_structure_drops_the_organism_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, recorded_organisms("vectorbase"))
    calls = play("frame", "vectorbase", _MESSAGE)
    state = AgentToolState()
    for call in _bindings(calls):
        criterion = _bound(call)
        state.frame_set_criterion(criterion)
        state.register_search(
            criterion.search_name,
            SearchOverview(
                search_name=criterion.search_name,
                display_name=criterion.search_name,
                record_type="transcript",
                description="",
                parameter_names=list(criterion.resolved_params),
                required_params=[],
            ),
        )
    root = StructureNode.model_validate(args_of(calls, "set_structure")[0]["root"])

    result = returned(
        await set_structure(
            agent_run_context(site_id="vectorbase", agent_state=state), root=root
        ),
        SetStructureResult,
    )

    assert result.criteria_combined == 1
    assert [(d.criterion_id, d.met) for d in result.dropped] == [
        ("organism_genes", True)
    ]
    assert [c.id for c in state.operational_spec_draft.criteria] == ["signal_peptide"]


def test_a_proposal_says_why_by_a_value_beside_the_marked_organism() -> None:
    state = AgentToolState()
    sheet = [
        SheetEntry(
            name="organism",
            display_name="Organism",
            type="multi-pick-vocabulary",
            required=True,
            organism_param=True,
        ),
        SheetEntry(name="min_tm", display_name="Min TM", type="string", required=True),
    ]
    state.pin_sheet("tm_domains", TM_DOMAINS, sheet, what_runs=TM_DOMAINS)
    pinned = pinned_frame_sheets(agent_run_context(agent_state=state)) or ""
    criterion = tm_domains(SiteValues.for_site("vectorbase"), "2", "99")

    args = proposal_args(criterion, dict.fromkeys(["organism", "min_tm"]), pinned)

    assert args["why"]["term"] == "min_tm"
