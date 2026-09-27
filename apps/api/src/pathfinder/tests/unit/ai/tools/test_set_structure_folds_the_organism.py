"""``set_structure`` drops an INTERSECT input that states only the organism its
sibling runs on, or matches every gene of it, removes its criterion and says
what became of its text."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.ledger_sections import unexpressed_words
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.tests._support.organism_reads import (
    serve_organism_reads,
    serve_universe_counts,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

PEST = "Anopheles gambiae PEST"
# The organisms vectorbase declares, as the intent gate reads them.
ORGANISMS = [PEST, "Anopheles stephensi Indian", "Aedes aegypti LVP_AGWG"]
# The genes of PEST, as vectorbase's organism search counts them.
PEST_GENES = 13_845


def _organism_rationale(search_name: str) -> SearchRationale:
    return SearchRationale(
        search_name=search_name,
        basis="parameter",
        term="Organism",
        reason=f"Organism is {PEST} for the search.",
        tool_call_id="call_bind",
    )


def _pest_universe(text: str) -> Criterion:
    return Criterion(
        id="c_pest",
        text=text,
        search_name="GenesByGeneModelChars",
        organism_param="organism_select_none",
        resolved_params={
            "organism_select_none": MultiPickValue(values=[PEST]),
            "gene_model_char": StringValue(value='{"filters":[]}'),
        },
        defaulted_params=["gene_model_char"],
        result_count=PEST_GENES,
        rationale=_organism_rationale("GenesByGeneModelChars"),
    )


def _signal(*, defaulted: bool = False) -> Criterion:
    """The signal peptide search; ``defaulted`` leaves every value but the
    organism at its default, which still matches 627 of the PEST genes."""
    return Criterion(
        id="c_signal",
        text="proteins with a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": MultiPickValue(values=[PEST]),
            "signalp_version": SinglePickValue(value="SignalP-6.0"),
        },
        defaulted_params=["signalp_version"] if defaulted else [],
        result_count=627,
        rationale=_organism_rationale("GenesWithSignalPeptide") if defaulted else None,
    )


def _tm() -> Criterion:
    return Criterion(
        id="c_tm",
        text="proteins with 2 to 99 transmembrane domains",
        search_name="GenesByTransmembraneDomains",
        organism_param="organism",
        resolved_params={
            "organism": MultiPickValue(values=[PEST]),
            "min_tm": StringValue(value="2"),
            "max_tm": StringValue(value="99"),
        },
        result_count=1_214,
    )


def _state(*criteria: Criterion) -> AgentToolState:
    state = AgentToolState()
    for criterion in criteria:
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
    return state


def _intersect(left: str = "c_pest", right: str = "c_signal") -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(kind="leaf", criterion_id=left),
            StructureNode(kind="leaf", criterion_id=right),
        ],
    )


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return serve_organism_reads(monkeypatch, ORGANISMS)


@pytest.fixture
def universe(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, str, str, tuple[str, ...]]]:
    return serve_universe_counts(monkeypatch, {(PEST,): PEST_GENES})


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(site_id="vectorbase", agent_state=state)


async def test_a_leaf_naming_only_the_organism_leaves_the_tree_and_the_criteria(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    del universe
    state = _state(_pest_universe(f"{PEST} genes"), _signal())

    result = returned(
        await set_structure(_ctx(state), root=_intersect()), SetStructureResult
    )

    draft = state.operational_spec_draft
    assert draft.structure is not None
    assert draft.structure.root == StructureNode(kind="leaf", criterion_id="c_signal")
    assert [c.id for c in draft.criteria] == ["c_signal"]
    assert result.criteria_combined == 1
    fate = (
        f"c_pest ('{PEST} genes') is dropped: it names only the organism {PEST}, "
        f"which c_signal already runs on, so that organism value meets it."
    )
    assert [d.fate for d in result.dropped] == [fate]
    assert [(d.text, d.reason) for d in draft.dropped] == [(f"{PEST} genes", fate)]
    assert sorted(site) == ["organisms:vectorbase", "record types:vectorbase"]


async def test_a_binding_that_matches_every_gene_leaves_its_text_unexpressed(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    del site
    state = _state(_pest_universe("PEST gene annotation"), _signal())

    result = returned(
        await set_structure(_ctx(state), root=_intersect()), SetStructureResult
    )

    assert [d.met for d in result.dropped] == [False]
    assert universe == [("vectorbase", "transcript", "GenesByTaxon", (PEST,))]
    draft = state.operational_spec_draft
    assert [(c.id, c.unexpressed_qualifiers) for c in draft.criteria] == [
        ("c_signal", [])
    ]
    assert [(d.text, d.unexpressed) for d in draft.dropped] == [
        ("PEST gene annotation", True)
    ]
    assert unexpressed_words(draft) == ["PEST gene annotation"]


async def test_rebinding_the_carrier_keeps_the_dropped_text_unexpressed(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    del site, universe
    state = _state(_pest_universe("PEST gene annotation"), _signal())
    await set_structure(_ctx(state), root=_intersect())

    state.frame_set_criterion(_signal())

    assert unexpressed_words(state.operational_spec_draft) == ["PEST gene annotation"]


async def test_a_criterion_that_states_the_dropped_text_meets_it(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    del site, universe
    state = _state(_pest_universe("PEST gene annotation"), _signal())
    await set_structure(_ctx(state), root=_intersect())

    state.frame_set_criterion(
        _signal().model_copy(
            update={"id": "c_annotation", "text": "genes with PEST gene annotation"}
        )
    )

    assert unexpressed_words(state.operational_spec_draft) == []


async def test_an_organism_only_filter_that_narrows_its_organism_stays(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    """The organism as the recorded reason drops nothing; the count decides."""
    del site
    state = _state(_signal(defaulted=True), _tm())

    result = returned(
        await set_structure(_ctx(state), root=_intersect("c_signal", "c_tm")),
        SetStructureResult,
    )

    assert (result.criteria_combined, result.dropped) == (2, [])
    assert [c.id for c in state.operational_spec_draft.criteria] == [
        "c_signal",
        "c_tm",
    ]
    assert universe == [("vectorbase", "transcript", "GenesByTaxon", (PEST,))]


async def test_a_tree_with_no_organism_only_input_counts_nothing(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    state = _state(_signal(), _tm())

    await set_structure(_ctx(state), root=_intersect("c_signal", "c_tm"))

    assert (len(site), universe) == (2, [])


async def test_a_tree_with_no_organism_candidate_reads_nothing(
    site: list[str], universe: list[tuple[str, str, str, tuple[str, ...]]]
) -> None:
    state = _state(_signal())

    await set_structure(
        _ctx(state), root=StructureNode(kind="leaf", criterion_id="c_signal")
    )

    assert (site, universe) == ([], [])
