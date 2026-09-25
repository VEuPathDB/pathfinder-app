"""A ``basis="parameter"`` why whose term is a value the call sets is refused
with the display name that value belongs to.

The call is the one a PlasmoDB framing pass made: GenesByGoTerm, with the GO id
set on ``go_typeahead`` and passed again as the term. The sheet's names and
display names are PlasmoDB's own, read from
``record-types/transcript/searches/GenesByGoTerm``.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    choice,
    match,
    read,
    refused,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    param_info,
    serve_search,
    serve_site_listing,
)

_KINASE = "GO:0004672"
GO_TERM = match(
    "GenesByGoTerm",
    "GO Term",
    "Find genes by Gene Ontology term.",
    0.52,
)
_LIVE_PARAMS: dict[str, str | list[str] | None] = {
    "organism": ["Plasmodium falciparum 3D7"],
    "go_term_evidence": None,
    "go_term_slim": None,
    "go_typeahead": [_KINASE],
    "go_term": None,
}


def _go_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=[
                VocabOption(
                    value="Plasmodium falciparum 3D7", display="P. falciparum 3D7"
                )
            ],
        ),
        param_info(
            "go_term_evidence",
            "multi-pick-vocabulary",
            display_name="Evidence",
            required=False,
            vocab_leaves=[
                VocabOption(value="Curated", display="Curated"),
                VocabOption(value="Computed", display="Computed"),
            ],
            default_value='["Curated", "Computed"]',
        ),
        param_info(
            "go_term_slim",
            "single-pick-vocabulary",
            display_name="Limit to GO Slim terms",
            required=False,
            vocab_leaves=[
                VocabOption(value="No", display="No"),
                VocabOption(value="Yes", display="Yes"),
            ],
            default_value="No",
        ),
        param_info(
            "go_typeahead",
            "multi-pick-vocabulary",
            display_name="GO Term or GO ID",
            vocab_leaves=[
                VocabOption(value=_KINASE, display="protein kinase activity")
            ],
        ),
        param_info(
            "go_term",
            display_name="GO Term wildcard search",
            required=False,
            default_value="N/A",
        ),
    ]


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _go_sheet)
    serve_site_listing(
        monkeypatch, [{"name": GO_TERM.name, "displayName": GO_TERM.display_name}]
    )


@pytest.mark.asyncio
async def test_the_go_id_passed_as_the_term_names_the_parameter_it_is_set_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, GO_TERM, query="protein kinase activity")

    refusal = await refused(
        state,
        choice(
            "parameter",
            _KINASE,
            "This search directly matches protein kinase activity; the organism "
            "is set to P. falciparum 3D7.",
        ),
        search_name=GO_TERM.name,
        params=_LIVE_PARAMS,
    )

    assert refusal == (
        "c_gpi: GO:0004672 is a value this call sets on GO Term or GO ID, not a "
        "parameter. Pass the term 'GO Term or GO ID' with basis parameter, and "
        "keep GO:0004672 in the reason."
    )


@pytest.mark.asyncio
async def test_a_term_no_parameter_holds_lists_the_display_names_it_may_take(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, GO_TERM, query="protein kinase activity")

    refusal = await refused(
        state,
        choice("parameter", "kinase", "sets kinase"),
        search_name=GO_TERM.name,
        params=_LIVE_PARAMS,
    )

    assert refusal == (
        "c_gpi: kinase is not a parameter of GenesByGoTerm. With basis parameter "
        "the term is the display name of a parameter this call sets: Organism, "
        "GO Term or GO ID. A value goes in the reason, never in the term."
    )
