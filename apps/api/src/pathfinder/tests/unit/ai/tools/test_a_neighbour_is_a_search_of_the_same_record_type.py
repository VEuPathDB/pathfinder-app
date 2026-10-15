"""A bound search's neighbours are searches of its own record type: a group bind
on qa.orthomcl.org does not read the BLAST sheets open beside it."""

from __future__ import annotations

from pydantic_ai import RunContext

from pathfinder.ai.agents.state import (
    AgentToolState,
    CatalogHit,
    CatalogRead,
    PinnedSheet,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_qualifiers import _sibling_names

from .conftest import agent_run_context


def _read(record_type: str, *hits: tuple[str, str]) -> CatalogRead:
    return CatalogRead(
        tool_call_id=f"call_{record_type}",
        tool="search_for_searches",
        query="map proteins to ortholog groups",
        record_type=record_type,
        hits=[
            CatalogHit(name=name, display_name=name, record_type=listed)
            for name, listed in hits
        ],
    )


def _ctx() -> RunContext[AgentDeps]:
    state = AgentToolState(
        catalog_reads=[
            _read("sequence", ("ByBlast", "sequence"), ("ByMotif", "sequence")),
            _read(
                "group",
                ("GroupsFromSequences", "group"),
                ("GroupsBySimilarity", "group"),
                ("GroupsByEValue", "group"),
            ),
        ],
        open_sheets={
            "c_prot1_hits": PinnedSheet(search_name="ByBlast", opened=True),
            "c_groups_alt": PinnedSheet(search_name="GroupsByEValue", opened=True),
        },
    )
    return agent_run_context(agent_state=state)


def test_a_sheet_of_another_record_type_is_no_neighbour() -> None:
    assert _sibling_names(_ctx(), "group", "GroupsFromSequences") == {
        "GroupsBySimilarity",
        "GroupsByEValue",
    }


def test_the_protein_side_keeps_its_own_neighbours() -> None:
    assert _sibling_names(_ctx(), "sequence", "ByBlast") == {"ByMotif"}
