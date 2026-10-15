"""A record type term may be any name the site shows the record type by, so
"ortholog groups" backs GroupsFromSequences on qa.orthomcl.org."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKRecordType

from pathfinder.ai.agents.state import CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone import _frame_rationale
from pathfinder.ai.tools.standalone._frame_rationale_terms import (
    Binding,
    ChosenTerm,
    checked_term,
)

_GROUPS = CatalogHit(
    name="GroupsFromSequences",
    display_name="Ortholog Groups from Proteins",
    record_type="group",
)
_BLAST = CatalogHit(name="ByBlast", display_name="BLAST", record_type="sequence")


def _binding() -> Binding:
    return Binding(
        criterion_id="c_prot1_groups",
        search_name="GroupsFromSequences",
        record_type="group",
        read=CatalogRead(
            tool_call_id="call_read",
            tool="search_for_searches",
            query="map proteins to ortholog groups",
            record_type="group",
            hits=[_GROUPS, _BLAST],
        ),
        bound=_GROUPS,
        infos=[],
        params={},
        values={},
        defaulted=[],
        transform=True,
        record_names=["group", "Ortholog Group", "Ortholog Groups"],
    )


@pytest.mark.parametrize("term", ["Ortholog groups", "ortholog group", "group"])
def test_any_name_the_site_shows_backs_the_record_type(term: str) -> None:
    assert checked_term("record_type", term, _binding()) == ChosenTerm(
        basis="record_type", term=term
    )


def test_a_name_the_site_does_not_show_is_refused_with_the_names_it_does() -> None:
    with pytest.raises(ModelRetry) as refused:
        checked_term("record_type", "proteins", _binding())

    assert str(refused.value) == (
        "c_prot1_groups: GroupsFromSequences returns group, not proteins. With "
        "basis record_type the term is one of: group, Ortholog Group, Ortholog Groups."
    )


async def test_the_names_are_read_from_the_sites_record_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = WDKRecordType(
        url_segment="group",
        display_name="Ortholog Group",
        display_name_plural="Ortholog Groups",
        short_display_name="Ortholog Group",
    )
    monkeypatch.setattr(
        _frame_rationale, "get_raw_record_types", AsyncMock(return_value=[group])
    )

    assert await _frame_rationale._record_names("orthomcl", "group") == [
        "group",
        "Ortholog Group",
        "Ortholog Groups",
    ]
