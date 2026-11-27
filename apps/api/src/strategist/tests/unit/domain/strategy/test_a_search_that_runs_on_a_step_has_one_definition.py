"""Whether a search runs on an input step is read in one function, and the node
a criterion takes in the tree follows from its role on the criterion itself."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from veupathdb.wdk import WDKSearch

from strategist.domain.strategy.operational_spec import Criterion, CriterionRole
from strategist.services.strategies import record_classes
from strategist.services.strategies.record_classes import (
    input_classes,
    takes_an_input_step,
)

_SOURCE = Path(record_classes.__file__).resolve().parents[2]
_ATTRIBUTE = "allowed_primary_input_record_class_names"


def _search(classes: list[str] | None) -> WDKSearch:
    return WDKSearch.model_validate(
        {
            "urlSegment": "GenesByOrthologs",
            "displayName": "Orthologs",
            "allowedPrimaryInputRecordClassNames": classes,
        }
    )


@pytest.mark.parametrize(
    ("classes", "takes"), [(["transcript"], True), ([], False), (None, False)]
)
def test_a_search_runs_on_a_step_when_it_names_an_input_class(
    classes: list[str] | None, takes: bool
) -> None:
    search = _search(classes)

    assert (takes_an_input_step(search), input_classes(search)) == (
        takes,
        frozenset(classes or ()),
    )


@pytest.mark.parametrize(
    ("role", "kind"),
    [
        ("transform", "transform"),
        ("seed", "leaf"),
        ("filter", "leaf"),
        ("exclude", "leaf"),
    ],
)
def test_a_criterion_takes_the_node_its_role_names(
    role: CriterionRole, kind: str
) -> None:
    assert Criterion(id="c", text="t", role=role).node_kind == kind


def _reads_the_attribute(path: Path) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr == _ATTRIBUTE
        for node in ast.walk(ast.parse(path.read_text()))
    )


def test_the_input_classes_are_read_in_one_module() -> None:
    reading = sorted(
        str(path.relative_to(_SOURCE))
        for path in _SOURCE.rglob("*.py")
        if "tests" not in path.parts and _reads_the_attribute(path)
    )

    assert reading == ["services/strategies/record_classes.py"]
