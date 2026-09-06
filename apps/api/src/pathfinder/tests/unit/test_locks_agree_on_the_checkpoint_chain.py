"""The app installs the checkpoint chain the runtime package pins."""

from __future__ import annotations

from importlib.metadata import distribution, version

import pytest
from packaging.requirements import Requirement

# assistant_core owns the checkpoint serializer and its suite is the gate that
# decides whether a state type survives a round trip. A gate that runs another
# version than the app proves nothing about the app.
LANGGRAPH = "langgraph"


def _runtime_langgraph_requirements() -> list[Requirement]:
    declared = distribution("assistant-core").requires or []
    parsed = [Requirement(raw) for raw in declared]
    return sorted(
        (one for one in parsed if one.name.split("-")[0] == LANGGRAPH),
        key=lambda one: one.name,
    )


def test_the_runtime_pins_the_checkpoint_chain() -> None:
    names = {one.name for one in _runtime_langgraph_requirements()}

    assert "langgraph-checkpoint" in names
    assert "langgraph-checkpoint-postgres" in names


@pytest.mark.parametrize(
    "requirement",
    _runtime_langgraph_requirements(),
    ids=lambda one: one.name,
)
def test_the_installed_version_is_the_one_the_runtime_names(
    requirement: Requirement,
) -> None:
    """A range would let the app and the runtime's gate diverge."""
    assert {str(one.operator) for one in requirement.specifier} == {"=="}
    assert version(requirement.name) in requirement.specifier
