"""``set_criterion`` shows FRAME a long open slot as the request's shortlist and
keeps the whole vocabulary on the criterion the card reads."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, VocabOption
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed, shortlist

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.operational_spec import OpenSlot
from pathfinder.tests._support.qa_recording import client_recording
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    serve_resolution,
    serve_search,
)

_PF3D7 = "Plasmodium falciparum 3D7"
_TEXT = "falciparum 3D7 genes with many exons"


def _organisms(fixture: str, param: str) -> list[VocabOption]:
    body = client_recording(fixture).json_body()
    infos = format_param_info_typed(
        WDKSearchResponse.model_validate(body).search_data.parameters or []
    )
    return next(info for info in infos if info.name == param).vocabulary()


def _portal_organisms() -> list[str]:
    """VectorBase's organisms listed before PlasmoDB's, as one portal vocabulary."""
    return [
        option.value
        for option in (
            *_organisms("search_genes_by_gene_model_chars", "organism_select_none"),
            *_organisms("search_genes_by_exon_count", "organism"),
        )
    ]


async def test_a_long_slot_reaches_frame_shortlisted_and_the_card_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organisms = _portal_organisms()
    serve_search(monkeypatch, lambda _context: [])
    serve_resolution(
        monkeypatch,
        {"scope": MultiPickValue(values=["Transcript"])},
        open_slots=[OpenSlot(param_name="organism", options=organisms)],
        unresolved=["organism"],
    )
    state = AgentToolState()

    result = await bind(state, "GenesByExonCount", {}, text=_TEXT)

    [shown] = result.open_slots
    wanted = shortlist([VocabOption(value=v, display=v) for v in organisms], _TEXT)
    assert len(organisms) == 279
    assert organisms.index(_PF3D7) == 214
    assert shown.options == [option.value for option in wanted]
    assert shown.options[0] == _PF3D7
    assert len(shown.options) < len(organisms)
    assert "279 values" in shown.question
    [held] = state.operational_spec_draft.criteria[0].open_params
    assert held.options == organisms
    assert "279 values" not in held.question
