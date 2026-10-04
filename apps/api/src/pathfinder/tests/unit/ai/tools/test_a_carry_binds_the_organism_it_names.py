"""A transform the message carries the genes through binds the organism entry
the message names, read by the stated-organism rule. A name the transform's
organism vocabulary lacks is refused with the nearest entries."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.orthology_request import OrthologyRequest
from pathfinder.tests._support.recorded_searches import (
    client_search,
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

# plasmodb's orthology transform: its organism tree reaches the Plasmodiidae.
_ORTHOLOGS = client_search("search_genes_by_orthologs")
_SIGNAL = suite_search("search_genes_with_signal_peptide")
_P01 = "Plasmodium vivax P01"
_PF3D7 = "Plasmodium falciparum 3D7"


def _bind(definition: WDKSearch, carried_to: str, organisms: list[str]) -> list[str]:
    """The organisms the call binds; a refusal raises instead."""
    call = CriterionCall(
        criterion_id="c_to",
        search_name=definition.url_segment,
        text="their syntenic orthologs",
        params={"organism": organisms, "isSyntenic": "yes"},
    )
    infos = format_param_info_typed(definition.parameters or [])
    refuse_what_the_words_decide(definition, call, infos, _carrying(carried_to))
    return organisms


def _carrying(target: str) -> AgentToolState:
    """A pass whose message carries the genes to ``target``."""
    return AgentToolState(
        orthology_request=OrthologyRequest(shape="transform", target=target)
    )


def test_the_entry_the_carry_names_binds() -> None:
    assert _bind(_ORTHOLOGS, _P01, [_P01]) == [_P01]


def test_a_strain_under_the_species_the_carry_names_binds() -> None:
    assert _bind(_ORTHOLOGS, "P. vivax", [_P01]) == [_P01]


def test_the_source_organism_in_place_of_the_carried_one_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_ORTHOLOGS, _P01, [_PF3D7])

    assert refused.value.message == (
        f"Organism on GenesByOrthologs binds ['{_PF3D7}'], and the request "
        f"carries the genes to '{_P01}'. A transform's organism is the organism "
        "of the genes it returns: bind the entry the request names."
    )


def test_a_carry_bound_to_no_organism_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_ORTHOLOGS, _P01, [])

    assert refused.value.message.startswith(
        f"Organism on GenesByOrthologs binds [], and the request carries the "
        f"genes to '{_P01}'."
    )


def test_an_organism_the_vocabulary_lacks_names_the_nearest_entries() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_ORTHOLOGS, "Toxoplasma gondii ME49", [_PF3D7])

    assert refused.value.message == (
        f"Organism on GenesByOrthologs binds ['{_PF3D7}'], and the request "
        "carries the genes to 'Toxoplasma gondii ME49', which this vocabulary "
        "lacks. Nearest entries: ['Plasmodiidae', 'Plasmodium', 'Plasmodium "
        "inui', 'Plasmodium vivax PAM', 'Plasmodium vivax']. Bind the organism "
        "the request names, or ask the researcher which entry they mean."
    )


def test_no_carry_leaves_the_transform_organism_alone() -> None:
    assert _bind(_ORTHOLOGS, "", [_PF3D7]) == [_PF3D7]


def test_a_search_that_takes_no_input_is_no_carry() -> None:
    call = CriterionCall(
        criterion_id="c_signal",
        search_name=_SIGNAL.url_segment,
        text="genes with a signal peptide",
        params={"organism": [_PF3D7]},
    )
    infos = format_param_info_typed(_SIGNAL.parameters or [])

    refuse_what_the_words_decide(_SIGNAL, call, infos, _carrying(_P01))

    assert call.params == {"organism": [_PF3D7]}


_CARRY = f"Carry these to their syntenic orthologs in {_P01}."


def _carrying_state() -> AgentToolState:
    state = AgentToolState(request_messages=[_CARRY])
    state.orthology_request = OrthologyRequest.read(_CARRY)
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_orthology",
            tool="search_for_searches",
            record_type="transcript",
            query="syntenic orthologs Plasmodium vivax",
            hits=[
                CatalogHit(
                    name="GenesByOrthologs",
                    display_name=_ORTHOLOGS.display_name,
                    record_type="transcript",
                )
            ],
        )
    )
    return state


@pytest.mark.asyncio
async def test_set_criterion_refuses_a_carry_bound_to_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded(monkeypatch, [_ORTHOLOGS])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_ORTHOLOGS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])
    state = _carrying_state()

    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_to_pviv",
            text="their syntenic orthologs in Plasmodium vivax P01",
            search_name="GenesByOrthologs",
            role="transform",
            params={"organism": [_PF3D7], "isSyntenic": "yes"},
            why=SearchChoice(
                basis="only_match",
                term="syntenic orthologs",
                reason="the one orthology transform the catalog answered",
            ),
        )

    assert refused.value.message.startswith(
        f"Organism on GenesByOrthologs binds ['{_PF3D7}'], and the request "
        f"carries the genes to '{_P01}'."
    )
    assert state.operational_spec_draft.criteria == []
