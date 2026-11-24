from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, VocabOption

from strategist.domain.strategy.stated_source import StatedSource
from strategist.domain.strategy.value_source import ParamSheet, value_source

_E10 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "e10_domain_database.json"
    ).read_text()
)
_DATABASES = ParamSheet(
    display_name="Domain Database",
    vocabulary=tuple(
        VocabOption.model_validate(v) for v in _E10["domainDatabase"]["vocabulary"]
    ),
)
_PF3D7 = "Plasmodium falciparum 3D7"
_PVP01 = "Plasmodium vivax P01"
_ORGANISMS = tuple(
    VocabOption(value=name, display=name)
    for name in (_PF3D7, _PVP01, "Plasmodium knowlesi strain H")
)
_COMPARE = f"Compare {_PF3D7} versus {_PVP01} kinases."


@pytest.mark.parametrize(
    "message",
    ["An InterPro and/or Pfam search.", "An InterPro (or Pfam) search."],
)
def test_pfam_at_the_default_beside_a_named_alternative_is_chosen(message: str) -> None:
    found = value_source(
        SinglePickValue(value="Pfam"),
        placeholder=False,
        unset=True,
        request_texts=[message],
        sheet=_DATABASES,
    )

    assert found == "chosen"


def test_a_side_of_a_comparison_another_criterion_binds_is_stated() -> None:
    found = value_source(
        MultiPickValue(values=[_PF3D7]),
        placeholder=False,
        unset=False,
        request_texts=[_COMPARE],
        sheet=ParamSheet(
            display_name="Organism",
            vocabulary=_ORGANISMS,
            taken_elsewhere=frozenset({_PVP01}),
        ),
    )

    assert found == StatedSource(words=_PF3D7)


def test_a_side_of_a_comparison_no_other_criterion_binds_is_chosen() -> None:
    found = value_source(
        MultiPickValue(values=[_PF3D7]),
        placeholder=False,
        unset=False,
        request_texts=[_COMPARE],
        sheet=ParamSheet(display_name="Organism", vocabulary=_ORGANISMS),
    )

    assert found == "chosen"
