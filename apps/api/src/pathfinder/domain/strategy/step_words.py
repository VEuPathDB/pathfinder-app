"""The researcher's words each step stands for, beside the search it runs."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pydantic import ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import OperationalSpec

__all__ = ["AddedSearch", "StepWords", "added_searches", "criterion_texts"]


class StepWords(CamelModel):
    """The metadata a stored strategy carries: the criterion text per step id."""

    model_config = ConfigDict(extra="ignore")

    criterion_texts: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def of(cls, ast: StrategyAst) -> StepWords:
        return cls.model_validate(ast.metadata or {})


class AddedSearch(CamelModel):
    """A step a turn added, the search it runs, and the words it stands for."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    search_display_name: str
    criterion_text: str


def criterion_texts(
    spec: OperationalSpec, step_id_by_criterion: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The words of every criterion that runs a search, keyed by its step id.

    A criterion id is its step id once the strategy is built; a build names
    the step each criterion minted.
    """
    minted = step_id_by_criterion or {}
    return {minted.get(c.id, c.id): c.text for c in spec.criteria if c.search_name}


def added_searches(
    spec: OperationalSpec, step_ids: Collection[str]
) -> list[AddedSearch]:
    """The searches the named steps run, for criteria whose search has a name."""
    return [
        AddedSearch(
            step_id=c.id,
            search_display_name=c.search_display_name,
            criterion_text=c.text,
        )
        for c in spec.criteria
        if c.id in step_ids and c.search_name and c.search_display_name
    ]
