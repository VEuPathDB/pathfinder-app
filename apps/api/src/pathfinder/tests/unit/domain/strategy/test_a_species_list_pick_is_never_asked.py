from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import VocabPick

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.vocab_picks import (
    PickRead,
    spec_held_open,
    unsettled_questions,
)

_SEARCH = "GenesByOrthologPattern"
_CODES = "padl, pbbi, pber"


def _pick(param_name: str) -> PickRead:
    return PickRead(
        search_name=_SEARCH,
        param_name=param_name,
        requirement="a group of genomes",
        pick=VocabPick(
            value="padl",
            display="a genome",
            choice_confidence=0.25,
            min_confidence=0.5,
            offered=8,
        ),
    )


def _criterion(param_name: str) -> Criterion:
    return Criterion(
        id="c1",
        text="genes with an ortholog in a group",
        search_name=_SEARCH,
        resolved_params={
            param_name: BoundValue(value=StringValue(value=_CODES), source="chosen")
        },
    )


def test_a_doubted_pick_on_a_species_list_holds_its_codes() -> None:
    criterion = _criterion("included_species")
    picks = [_pick("included_species")]
    spec = OperationalSpec(criteria=[criterion])
    assert unsettled_questions([criterion], picks, []) == []
    assert spec_held_open(spec, picks) == spec


def test_the_read_tells_frame_a_species_list_is_bound_from_its_codes() -> None:
    assert _pick("excluded_species").note() == (
        "A species list is bound from its genome and clade codes, so this read "
        "settles nothing and is not asked of the researcher."
    )


def test_a_doubted_pick_on_another_parameter_is_still_asked() -> None:
    criterion = _criterion("domain_typeahead")
    picks = [_pick("domain_typeahead")]
    asked = unsettled_questions([criterion], picks, [])
    assert [q.param_name for q in asked] == ["domain_typeahead"]
