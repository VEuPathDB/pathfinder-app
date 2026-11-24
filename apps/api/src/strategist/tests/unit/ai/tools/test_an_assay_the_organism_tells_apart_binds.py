from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    flatten_vocab,
    read_options,
    vocab_paths,
)
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearch, WDKSearchResponse

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_lookups import pick_problems
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.tests._support.param_infos import sheet_of

_SEARCH = "GenesByMassSpec"
_ASSAY = "ms_assay"
_PF3D7 = "female gametocytes_Plasmodium falciparum 3D7"
_MESSAGE = (
    "Proteins detected by mass spec in female gametocytes of Plasmodium falciparum 3D7."
)


def _mass_spec() -> WDKSearch:
    body = load_recorded("search_genes_by_mass_spec").json_body()
    return WDKSearchResponse.model_validate(body).search_data


def test_the_pf3d7_assay_binds_alone_when_the_request_names_pf3d7() -> None:
    definition = _mass_spec()
    [assay] = [p for p in definition.parameters or [] if p.name == _ASSAY]
    options = flatten_vocab(assay.vocabulary)
    read = read_options(
        options,
        ["female gametocytes"],
        request_terms=[],
        under=vocab_paths(assay.vocabulary),
    )
    assert read.lookup is not None
    state = AgentToolState()
    state.request_messages = [_MESSAGE]
    state.record_lookup(_SEARCH, _ASSAY, read.lookup, options)
    call = CriterionCall(
        criterion_id="c_female_gametocytes",
        search_name=_SEARCH,
        text=_MESSAGE,
        params={},
    ).with_values({_ASSAY: MultiPickValue(values=[_PF3D7])})

    problems = pick_problems(
        state, definition, call, sheet_of(definition.parameters or [])
    )

    assert state.looked_up[(_SEARCH, _ASSAY)].same_named == {}
    assert [p.key.check for p in problems.found] == []
