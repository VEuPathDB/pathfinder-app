"""The researcher's words each step stands for, and why it runs its search."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pydantic import ConfigDict, Field, OnErrorOmit
from veupathdb.domain.strategy import StrategyAst
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.step_rationale import SearchRationale, StepRationale

__all__ = [
    "AddedSearch",
    "StampedKind",
    "StepWords",
    "added_searches",
    "step_words",
]


class StampedKind(CamelModel):
    """An analysis kind, and the search it was read for.

    WDK picks the plugin by the search's query, so a kind read for one search
    says nothing about a step that now runs another.
    """

    model_config = ConfigDict(frozen=True)

    search_name: str
    kind: AnalysisKind

    def for_search(self, search_name: str | None) -> AnalysisKind | None:
        """The kind, while the step still runs the search it was read for."""
        return self.kind if self.search_name == search_name else None


class StepWords(CamelModel):
    """The metadata a stored strategy carries per step id: the researcher's
    words, why the step runs its search, and which plugin reads the analysis
    document an EDA step carries.

    A stored kind or reason that does not parse is absent.
    """

    model_config = ConfigDict(extra="ignore")

    criterion_texts: dict[str, str] = Field(default_factory=dict)
    analysis_kinds: dict[str, OnErrorOmit[StampedKind]] = Field(default_factory=dict)
    rationales: dict[str, OnErrorOmit[SearchRationale]] = Field(default_factory=dict)

    @classmethod
    def of(cls, ast: StrategyAst) -> StepWords:
        return cls.model_validate(ast.metadata or {})

    @property
    def empty(self) -> bool:
        return not (self.criterion_texts or self.analysis_kinds or self.rationales)

    def kind_of(self, step_id: str, search_name: str | None) -> AnalysisKind | None:
        """The step's kind, when it was read for the search the step runs."""
        stamped = self.analysis_kinds.get(step_id)
        return None if stamped is None else stamped.for_search(search_name)

    def rationale_of(
        self, step_id: str, search_name: str | None
    ) -> SearchRationale | None:
        """Why the step runs its search, while it runs the search it was chosen for."""
        chosen = self.rationales.get(step_id)
        return (
            chosen if chosen is not None and chosen.search_name == search_name else None
        )

    def noted(self, newer: StepWords, step_ids: Collection[str]) -> StepWords:
        """These words with the newer ones over them, for the named steps only.

        A step the newer words speak for takes its reason from them, so a
        criterion that no longer holds one drops the old one.
        """
        held = set(step_ids)
        spoken = newer.criterion_texts.keys() | newer.rationales.keys()
        texts = self.criterion_texts | newer.criterion_texts
        kinds = self.analysis_kinds | newer.analysis_kinds
        kept = {s: r for s, r in self.rationales.items() if s not in spoken}
        rationales = kept | newer.rationales
        return StepWords(
            criterion_texts={s: t for s, t in texts.items() if s in held},
            analysis_kinds={s: k for s, k in kinds.items() if s in held},
            rationales={s: r for s, r in rationales.items() if s in held},
        )


class AddedSearch(CamelModel):
    """A step a turn added, the search it runs, the words it stands for, and
    why it runs that search."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    search_display_name: str
    criterion_text: str
    rationale: StepRationale | None = None


def step_words(
    spec: OperationalSpec, step_id_by_criterion: Mapping[str, str] | None = None
) -> StepWords:
    """The words and the reason of every criterion that runs a search, by step id.

    A criterion id is its step id once the strategy is built; a build names
    the step each criterion minted.
    """
    minted = step_id_by_criterion or {}
    searched = [c for c in spec.criteria if c.search_name]
    return StepWords(
        criterion_texts={minted.get(c.id, c.id): c.text for c in searched},
        rationales={
            minted.get(c.id, c.id): c.rationale
            for c in searched
            if c.rationale is not None
        },
    )


def added_searches(
    spec: OperationalSpec, step_ids: Collection[str]
) -> list[AddedSearch]:
    """The searches the named steps run, for criteria whose search has a name."""
    return [
        AddedSearch(
            step_id=c.id,
            search_display_name=c.search_display_name,
            criterion_text=c.text,
            rationale=c.step_rationale,
        )
        for c in spec.criteria
        if c.id in step_ids and c.search_name and c.search_display_name
    ]
