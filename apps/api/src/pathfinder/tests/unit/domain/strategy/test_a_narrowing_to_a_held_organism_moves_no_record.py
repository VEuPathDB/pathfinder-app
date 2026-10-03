"""An edit that narrows the result to organisms the held root already answers,
or widens it to organisms that hold every held one, moves no record to
another organism."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue

from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology import organism_move_refusal
from pathfinder.tests._support.bound_values import bound

_STEP = "step_d9b1efdc"
_PF3D7 = "Plasmodium falciparum 3D7"
# The organisms the veupathdb GO:0042540 step holds, as get_live_strategy_state read them.
_PLASMODIUM = [
    "Plasmodium adleri G01",
    "Plasmodium berghei ANKA",
    "Plasmodium billcollinsi G01",
    "Plasmodium blacklocki G01",
    "Plasmodium brasilianum strain Bolivian I",
    "Plasmodium chabaudi chabaudi",
    "Plasmodium chabaudi chabaudi CB",
    "Plasmodium coatneyi Hackeri",
    "Plasmodium cynomolgi strain B",
    "Plasmodium cynomolgi strain M",
    "Plasmodium falciparum 3D7",
    "Plasmodium falciparum 7G8",
    "Plasmodium falciparum 7G8 2019",
    "Plasmodium falciparum CD01",
    "Plasmodium falciparum Dd2",
    "Plasmodium falciparum GA01",
    "Plasmodium falciparum GB4",
    "Plasmodium falciparum GN01",
    "Plasmodium falciparum HB3",
    "Plasmodium falciparum IT",
    "Plasmodium falciparum KE01",
    "Plasmodium falciparum KH01",
    "Plasmodium falciparum KH02",
    "Plasmodium falciparum ML01",
    "Plasmodium falciparum NF135.C10",
    "Plasmodium falciparum NF166",
    "Plasmodium falciparum NF54",
    "Plasmodium falciparum SD01",
    "Plasmodium falciparum SN01",
    "Plasmodium falciparum TG01",
    "Plasmodium fragile strain nilgiri",
    "Plasmodium gaboni strain G01",
    "Plasmodium gaboni strain SY75",
    "Plasmodium gallinaceum 8A",
    "Plasmodium inui San Antonio 1",
    "Plasmodium knowlesi strain A1H1",
    "Plasmodium knowlesi strain H",
    "Plasmodium knowlesi strain Malayan Strain Pk1 A",
    "Plasmodium malariae UG01",
    "Plasmodium ovale curtisi GH01",
    "Plasmodium ovale wallikeri PowCR01",
    "Plasmodium praefalciparum strain G01",
    "Plasmodium reichenowi CDC",
    "Plasmodium reichenowi G01",
    "Plasmodium relictum SGS1-like",
    "Plasmodium vinckei brucechwatti DA",
    "Plasmodium vinckei Cameroon EL",
    "Plasmodium vinckei lentum DE",
    "Plasmodium vinckei petteri CR 2020",
    "Plasmodium vinckei petteri strain CR",
    "Plasmodium vinckei vinckei CY",
    "Plasmodium vinckei vinckei strain vinckei",
    "Plasmodium vivax P01",
    "Plasmodium vivax PAM",
    "Plasmodium vivax PvW1",
    "Plasmodium vivax Sal-1",
    "Plasmodium vivax-like Pvl01",
    "Plasmodium yoelii yoelii 17X",
    "Plasmodium yoelii yoelii 17XNL",
    "Plasmodium yoelii yoelii 17XNL 2023",
    "Plasmodium yoelii yoelii YM",
]


def _go_step(organisms: list[str]) -> OperationalSpec:
    """The one-step GenesByGoTerm strategy with the values set_criterion sent."""
    criterion = Criterion(
        id=_STEP,
        text="Genes across Plasmodium with the GO term 'hemoglobin catabolic process'.",
        search_name="GenesByGoTerm",
        search_display_name="GO Term",
        role="filter",
        organism_param="organism",
        resolved_params=bound(
            {
                "go_term": StringValue(value="N/A"),
                "go_term_evidence": MultiPickValue(values=["Curated", "Computed"]),
                "go_term_slim": SinglePickValue(value="No"),
                "go_typeahead": MultiPickValue(values=["GO:0042540"]),
                "organism": MultiPickValue(values=organisms),
            }
        ),
    )
    return OperationalSpec(
        goal=criterion.text,
        criteria=[criterion],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id=_STEP)),
    )


def test_a_narrowing_to_one_held_organism_is_not_refused() -> None:
    assert [
        organism_move_refusal(
            "tighten", before=_go_step(_PLASMODIUM), after=_go_step([_PF3D7])
        )
    ] == [None]


def test_a_widening_that_keeps_every_held_organism_is_not_refused() -> None:
    assert [
        organism_move_refusal(
            "loosen", before=_go_step([_PF3D7]), after=_go_step(_PLASMODIUM)
        )
    ] == [None]


@pytest.mark.parametrize(
    ("direction", "before", "after"),
    [
        ("tighten", [_PF3D7], ["Plasmodium vivax P01"]),
        ("tighten", [_PF3D7], _PLASMODIUM),
        ("loosen", _PLASMODIUM, [_PF3D7]),
    ],
)
def test_an_edit_against_its_direction_or_to_another_organism_is_refused(
    direction: EditDirection, before: list[str], after: list[str]
) -> None:
    refusal = organism_move_refusal(
        direction, before=_go_step(before), after=_go_step(after)
    )

    assert refusal is not None
    assert refusal.startswith(f"This edit asks to {direction} the result")
