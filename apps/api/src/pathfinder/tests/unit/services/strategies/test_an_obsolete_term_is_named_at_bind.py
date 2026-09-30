"""A pick whose site label marks it obsolete is named at the label read, with
the current entries of the vocabulary nearest its words."""

from __future__ import annotations

from pydantic import TypeAdapter
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.services.strategies.obsolete_terms import ObsoletePick, obsolete_picks
from pathfinder.services.strategies.value_labels import vocabulary_labels

# The go_typeahead parameter of TriTrypDB's GenesByGoTerm as the site serves
# it, its vocabulary cut to the entries these cases read.
_GO_TYPEAHEAD: WDKParameter = TypeAdapter(WDKParameter).validate_python(
    {
        "name": "go_typeahead",
        "displayName": "GO Term or GO ID",
        "type": "multi-pick-vocabulary",
        "displayType": "typeAhead",
        "minSelectedCount": 1,
        "maxSelectedCount": -1,
        "isVisible": True,
        "isReadOnly": False,
        "allowEmptyValue": False,
        "initialDisplayValue": "[]",
        "dependentParams": [],
        "group": "empty",
        "vocabulary": [
            ["GO:0009296", "GO:0009296 : obsolete flagellum assembly : 0", None],
            ["GO:0060271", "GO:0060271 : cilium assembly : 7", None],
            ["GO:0044458", "GO:0044458 : motile cilium assembly : 8", None],
            ["GO:0120316", "GO:0120316 : sperm flagellum assembly : 4", None],
            ["GO:0042255", "GO:0042255 : ribosome assembly : 8", None],
        ],
    }
)


def _read(term: str) -> list[ObsoletePick]:
    bound = {
        "go_typeahead": BoundValue(value=MultiPickValue(values=[term]), source="chosen")
    }
    infos = format_param_info_typed([_GO_TYPEAHEAD])
    return obsolete_picks(vocabulary_labels(bound, infos).labels, infos)


def test_a_term_the_site_labels_obsolete_is_named_with_the_current_entries() -> None:
    assert _read("GO:0009296") == [
        ObsoletePick(
            param="go_typeahead",
            term="GO:0009296",
            label="GO:0009296 : obsolete flagellum assembly : 0",
            nearest=[
                "GO:0060271 : cilium assembly : 7",
                "GO:0044458 : motile cilium assembly : 8",
                "GO:0120316 : sperm flagellum assembly : 4",
                "GO:0042255 : ribosome assembly : 8",
            ],
        )
    ]


def test_a_current_term_is_not_named() -> None:
    assert _read("GO:0060271") == []
