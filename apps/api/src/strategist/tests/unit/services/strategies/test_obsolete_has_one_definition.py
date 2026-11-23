from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.wdk import WDKParameter

from strategist.domain.strategy.operational_spec import BoundValue
from strategist.services.strategies.obsolete_terms import (
    OBSOLETE,
    obsolete_picks,
    says_obsolete,
)
from strategist.services.strategies.value_labels import vocabulary_labels
from strategist.tests._support.param_infos import sheet_of

_STRATEGIST = Path(__file__).resolve().parents[4]
_THE_HOME = "services/strategies/obsolete_terms.py"
_LATER_WORD = "GO:0000001 : kinase activity (obsolete) : 3"


def _go_typeahead(vocabulary: list[list[str | None]]) -> WDKParameter:
    return TypeAdapter(WDKParameter).validate_python(
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
            "vocabulary": vocabulary,
        }
    )


@pytest.mark.parametrize(
    ("value", "display", "obsolete"),
    [
        ("GO:0009405", "GO:0009405 : obsolete pathogenesis : 0", True),
        (
            "GO:0031225",
            "GO:0031225 : obsolete anchored component of membrane : 0",
            True,
        ),
        ("GO:0004682", "GO:0004682 : obsolete protein kinase CK2 activity : 0", True),
        ("GO:0060271", "GO:0060271 : cilium assembly : 7", False),
        ("GO:0000001", _LATER_WORD, False),
    ],
)
def test_a_label_is_obsolete_when_its_term_name_starts_with_the_word(
    value: str, display: str, *, obsolete: bool
) -> None:
    assert says_obsolete(value, display) is obsolete


def test_a_pick_whose_name_holds_the_word_later_is_current() -> None:
    param = _go_typeahead(
        [
            ["GO:0000001", _LATER_WORD, None],
            ["GO:0060271", "GO:0060271 : cilium assembly : 7", None],
        ]
    )
    infos = sheet_of([param])
    bound = {
        "go_typeahead": BoundValue(
            value=MultiPickValue(values=["GO:0000001"]), source="chosen"
        )
    }

    assert obsolete_picks(vocabulary_labels(bound, infos).labels, infos) == []


def _modules_writing_the_word() -> list[str]:
    found: list[str] = []
    for path in sorted(_STRATEGIST.rglob("*.py")):
        relative = path.relative_to(_STRATEGIST).as_posix()
        if relative.startswith("tests/"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            match node:
                case ast.Constant(value=str(text)) if text.strip() == OBSOLETE:
                    found.append(relative)
    return found


def test_one_module_defines_what_obsolete_means() -> None:
    assert _modules_writing_the_word() == [_THE_HOME]
