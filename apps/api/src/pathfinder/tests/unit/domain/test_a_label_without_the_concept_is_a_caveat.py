"""A chosen pick whose label holds no word of the looked-up concept is a
caveat, and it is not repeated as a note on the value's row."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.domain.caveats import caveats_for
from pathfinder.domain.strategy.measurement_clauses import counted_clauses
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
    ValueSource,
)
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.domain.value_caveats import LabelGapCaveat, assumed_value_caveats

_GO = "go_typeahead"
_PATHWAY = (
    "GO:0007200 : phospholipase C-activating G protein-coupled receptor "
    "signaling pathway : 5"
)
_GAP = Measurement(
    kind="label_without_the_concept",
    param=_GO,
    label=_PATHWAY,
    reading="'lipase', 'lipase activity'",
)


def _criterion(source: ValueSource) -> Criterion:
    return Criterion.model_validate(
        {
            "id": "c_lipase_annotation",
            "text": "Aspergillus nidulans FGSC A4 genes carrying a lipase annotation",
            "search_name": "GenesByGoTerm",
            "resolved_params": {
                _GO: BoundValue(
                    value=MultiPickValue(values=["GO:0016298", "GO:0007200"]),
                    source=source,
                )
            },
            "param_display_names": {_GO: "GO Term or GO ID"},
            "measurements": [_GAP],
            "result_count": 73,
        }
    )


def test_a_chosen_pick_without_the_concept_word_is_a_caveat() -> None:
    (caveat,) = assumed_value_caveats(OperationalSpec(criteria=[_criterion("chosen")]))

    assert caveat == LabelGapCaveat(
        criterion_id="c_lipase_annotation",
        param_display_name="GO Term or GO ID",
        value=_PATHWAY,
        source="chosen",
        reading="'lipase', 'lipase activity'",
    )
    assert caveat.sentence == (
        f"GO Term or GO ID took {_PATHWAY!r}, chosen, whose label holds no word "
        "of 'lipase', 'lipase activity'"
    )


def test_a_stated_pick_makes_no_label_caveat() -> None:
    spec = OperationalSpec(criteria=[_criterion("stated")])

    assert assumed_value_caveats(spec) == []


def test_the_caveat_travels_in_the_facts_and_not_as_a_row_note() -> None:
    spec = OperationalSpec(criteria=[_criterion("chosen")])
    facts = TurnFacts(caveats=caveats_for(spec, []))

    assert [c.kind for c in facts.caveats] == ["label_without_the_concept"]
    assert counted_clauses(_criterion("chosen"), _GO, noun="gene") == []
