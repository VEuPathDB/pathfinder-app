"""FRAME's structure fold through the real tools, read live: on vectorbase the
organism bound alone as a criterion leaves the tree, and on the portal a signal
peptide search bound on its organism alone stays, because it narrows it."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field

import pytest
from pydantic_ai import RunContext
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import organism_parameter

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.organism_universe import universe_counts
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

pytestmark = [pytest.mark.live_wdk]

_SITE = "vectorbase"
_PORTAL = "veupathdb"
PEST = "Anopheles gambiae PEST"
PF = "Plasmodium falciparum 3D7"
_GENE_MODEL = "GenesByGeneModelChars"
_SIGNAL = "GenesWithSignalPeptide"
_TM = "GenesByTransmembraneDomains"


@pytest.fixture
def registered(require_wdk_creds: str) -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def _ctx(state: AgentToolState, site_id: str = _SITE) -> RunContext[AgentDeps]:
    session = StrategySession(site_id=site_id)
    graph = StrategyGraph(graph_id="g1", name="g", site_id=site_id)
    graph.record_type = "transcript"
    session.add_graph(graph)
    return agent_run_context(
        site_id=site_id, agent_state=state, strategy_session=session
    )


def _read(*hits: CatalogHit) -> CatalogRead:
    """The catalog read FRAME bound the criteria from."""
    return CatalogRead(
        tool_call_id="call_read",
        tool="list_searches",
        record_type="transcript",
        hits=list(hits)
        or [
            CatalogHit(name=_GENE_MODEL, display_name="Gene Model Characteristics"),
            CatalogHit(name=_SIGNAL, display_name="Predicted Signal Peptide"),
        ],
    )


@dataclass(frozen=True)
class _Stated:
    """The organism a binding sets on its marked parameter, and its other values."""

    organism: str = PEST
    values: dict[str, str] = field(default_factory=dict)


async def _bound(
    ctx: RunContext[AgentDeps],
    criterion_id: str,
    text: str,
    search_name: str,
    why: SearchChoice,
    stated: _Stated | None = None,
) -> SetCriterionResult:
    """Read the sheet, then bind what ``stated`` holds, every other value null."""
    held = stated or _Stated()
    sheet = returned(
        await set_criterion(
            ctx, criterion_id=criterion_id, text=text, search_name=search_name
        ),
        SetCriterionResult,
    )
    marked = await organism_parameter(ctx.deps.site_id, "transcript", search_name)
    assert marked is not None
    params: dict[str, str | list[str] | None] = dict.fromkeys(
        sheet.params_template or {}
    )
    params[marked] = [held.organism]
    params.update(held.values)
    return returned(
        await set_criterion(
            ctx,
            criterion_id=criterion_id,
            text=text,
            search_name=search_name,
            params=params,
            why=why,
        ),
        SetCriterionResult,
    )


@pytest.mark.usefixtures("registered")
async def test_s1_frames_one_search_on_vectorbase() -> None:
    state = AgentToolState()
    state.record_catalog_read(_read())
    ctx = _ctx(state)

    universe = await _bound(
        ctx,
        "c_pest",
        f"{PEST} genes",
        _GENE_MODEL,
        SearchChoice(
            basis="parameter",
            term="Organism",
            reason=f"Organism is {PEST} for the gene-model search.",
        ),
    )
    signal = await _bound(
        ctx,
        "c_signal",
        "proteins with a predicted signal peptide",
        _SIGNAL,
        SearchChoice(
            basis="only_match",
            term="Signal Peptide",
            reason="Predicted Signal Peptide is the only search naming Signal Peptide.",
        ),
    )
    structure = returned(
        await set_structure(
            ctx,
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_pest"),
                    StructureNode(kind="leaf", criterion_id="c_signal"),
                ],
            ),
        ),
        SetStructureResult,
    )

    assert universe.rationale is not None
    assert (universe.rationale.basis, universe.rationale.term) == (
        "parameter",
        "Organism",
    )
    assert universe.result_count is not None
    assert signal.result_count is not None
    assert universe.result_count > signal.result_count
    genes = await universe_counts(_SITE, "transcript", [(PEST,)])
    assert genes == {(PEST,): universe.result_count}
    assert structure.criteria_combined == 1
    assert [(d.criterion_id, d.met) for d in structure.dropped] == [("c_pest", True)]
    draft = state.operational_spec_draft
    assert [(c.id, c.organism_param) for c in draft.criteria] == [
        ("c_signal", "organism")
    ]
    assert draft.structure is not None
    assert draft.structure.root == StructureNode(kind="leaf", criterion_id="c_signal")


@pytest.mark.usefixtures("registered")
async def test_a_signal_peptide_bound_on_its_organism_alone_stays_on_the_portal() -> (
    None
):
    state = AgentToolState()
    state.record_catalog_read(
        _read(
            CatalogHit(name=_SIGNAL, display_name="Predicted Signal Peptide"),
            CatalogHit(name=_TM, display_name="Transmembrane Domain Count"),
        )
    )
    ctx = _ctx(state, _PORTAL)

    signal = await _bound(
        ctx,
        "c_signal",
        "proteins with a predicted signal peptide",
        _SIGNAL,
        SearchChoice(
            basis="parameter",
            term="organism",
            reason="sets organism to the value the request states",
        ),
        _Stated(organism=PF),
    )
    tm = await _bound(
        ctx,
        "c_tm",
        "proteins with 2 to 99 transmembrane domains",
        _TM,
        SearchChoice(
            basis="parameter", term="min_tm", reason="sets min_tm to 2 as stated"
        ),
        _Stated(organism=PF, values={"min_tm": "2", "max_tm": "99"}),
    )
    structure = returned(
        await set_structure(
            ctx,
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_signal"),
                    StructureNode(kind="leaf", criterion_id="c_tm"),
                ],
            ),
        ),
        SetStructureResult,
    )

    genes = await universe_counts(_PORTAL, "transcript", [(PF,)])
    assert signal.result_count is not None
    assert tm.result_count is not None
    assert 0 < signal.result_count < genes[(PF,)]
    assert (structure.criteria_combined, structure.dropped) == (2, [])
    assert [c.id for c in state.operational_spec_draft.criteria] == [
        "c_signal",
        "c_tm",
    ]
