from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, VocabOption
from veupathdb_mcp.catalog import VocabPick

from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.vocab_picks import PickRead

_GO = [
    VocabOption(value="GO:0003824", display="GO:0003824 : catalytic activity : 2"),
    VocabOption(
        value="GO:0140098", display="GO:0140098 : catalytic activity, acting on RNA : 4"
    ),
    VocabOption(value="GO:0016740", display="GO:0016740 : transferase activity : 3"),
]
_INTERPRO = [
    VocabOption(value="IPR011009", display="IPR011009 : Protein kinase-like (PK-like)"),
    VocabOption(value="IPR000719", display="IPR000719 : Protein kinase domain"),
]


def _read(param: str, kept: list[VocabOption], requirement: str) -> PickRead:
    return PickRead(
        search_name="GenesBySomething",
        param_name=param,
        requirement=requirement,
        pick=VocabPick(
            value=kept[0].value,
            display=kept[0].display,
            choice_confidence=0.05,
            min_confidence=0.5,
            offered=len(kept),
        ),
        kept=kept,
    )


def _criterion(param: str, named: str, value: str) -> Criterion:
    return Criterion(
        id="c1",
        text="the requirement",
        search_name="GenesBySomething",
        resolved_params={
            param: BoundValue(value=MultiPickValue(values=[value]), source="chosen")
        },
        param_display_names={param: named},
    )


@pytest.mark.parametrize(
    ("param", "named", "kept", "requirement", "question", "labels"),
    [
        (
            "GoTerms",
            "GO Term or GO ID",
            _GO,
            "enzymes",
            (
                "Which GO Term or GO ID states 'enzymes'? On this site the nearest "
                "entry is catalytic activity. Pick an entry, or say in your own words "
                "what you mean."
            ),
            [
                "GO Term or GO ID catalytic activity",
                "GO Term or GO ID catalytic activity, acting on RNA",
                "GO Term or GO ID transferase activity",
            ],
        ),
        (
            "domain_typeahead",
            "Specific Domain(s)",
            _INTERPRO,
            "protein kinase",
            (
                "Which Specific Domain(s) states 'protein kinase'? On this site the "
                "nearest entry is Protein kinase-like (PK-like). Pick an entry, or say "
                "in your own words what you mean."
            ),
            [
                "Specific Domain(s) Protein kinase-like (PK-like)",
                "Specific Domain(s) Protein kinase domain",
            ],
        ),
    ],
)
def test_a_pick_card_names_entries_by_their_site_labels(
    param: str,
    named: str,
    kept: list[VocabOption],
    requirement: str,
    question: str,
    labels: list[str],
) -> None:
    criterion = _criterion(param, named, kept[0].value)

    asked = _read(param, kept, requirement).question(criterion)
    typed = asked.typed(criterion)

    assert asked.question == question
    assert [o.label for o in typed.options] == labels
    assert [o.binding.model_dump()["params"] for o in typed.options] == [
        {param: option.value} for option in kept
    ]


def test_the_read_still_tells_the_model_the_confidence() -> None:
    assert _read("GoTerms", _GO, "enzymes").note() == (
        "The nearest entry to 'enzymes' is GO:0003824 (GO:0003824 : catalytic "
        "activity : 2), confidence 0.05, which does not settle it, so a binding "
        "of this parameter is asked of the researcher."
    )
