from __future__ import annotations

import httpx
from veupathdb.domain.parameters import SHOWN_CANDIDATES, VocabOption, rank_entries
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    NamedVocabulary,
    ResolveContext,
    ordered_terms,
    post_decision,
    use_decisions_transport,
)

_ORGANISMS = [
    VocabOption(value=name, display=name)
    for name in (
        "Plasmodium falciparum 3D7",
        "Plasmodium falciparum Dd2",
        "Plasmodium falciparum HB3",
        "Plasmodium vivax P01",
        "Plasmodium knowlesi strain H",
        "Plasmodium berghei ANKA",
        "Toxoplasma gondii ME49",
    )
]
_PHRASE = "Plasmodium falciparum"
_REFUSED = httpx.ConnectError("connection refused")


async def _unanswered(request: DecisionRequest) -> DecisionResponse:
    del request
    raise _REFUSED


async def test_an_unanswered_decision_shows_the_ranking_and_picks_nothing() -> None:
    vocabulary = NamedVocabulary(display="ortholog organism", options=_ORGANISMS)
    use_decisions_transport(_unanswered)
    try:
        [ordered] = await ordered_terms(
            ResolveContext(site_id="plasmodb"), [(vocabulary, _PHRASE)]
        )
    finally:
        use_decisions_transport(post_decision)

    assert ordered == rank_entries(_ORGANISMS, _PHRASE, SHOWN_CANDIDATES)
    assert len(ordered) == SHOWN_CANDIDATES
