"""The operation models the model-facing batch carries, read from the union."""

from __future__ import annotations

from typing import get_args

from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operations import EditableOperation, GraphOperation


def editable_models() -> set[type[CamelModel]]:
    """Every model ``EditableOperation`` holds."""
    return set(get_args(get_args(EditableOperation)[0]))


def refused_models() -> set[type[CamelModel]]:
    """Every model a batch refuses: the wider union minus the editable one."""
    wider: set[type[CamelModel]] = set(get_args(get_args(GraphOperation)[0]))
    return wider - editable_models()
