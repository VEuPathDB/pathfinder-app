"""The small records one turn keeps: what it answered, emptied, ran and wrote."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.domain.eda_thread import EdaExport
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.step_words import AddedSearch


class ZeroResultStep(CamelModel):
    """A search that came back empty on some build of this thread."""

    search_name: str
    criterion_text: str = ""


class EnrichmentRun(CamelModel):
    """One enrichment a durable task answered, and what it named.

    A run that failed names the set it was asked for; a run that finished
    names the set the worker reports it analysed.
    """

    task_id: UUID
    gene_set_id: str
    gene_set_name: str = ""
    succeeded: bool = False


class CreatedControlSet(CamelModel):
    """A control set one turn wrote, as a reply that names it must read."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str


class AnsweredQuestions(CamelModel):
    """The questions one answer closed, and the words of that answer."""

    questions: list[OpenQuestion]
    answer: str
    # A card answers questions a pass asked under this same message.
    on_card: bool = False


class TurnMarkers(CamelModel):
    """What the Lead already did for one user message.

    The record belongs to the message it names. A turn answering a different
    message starts from an empty one, so nothing an earlier message unlocked
    is still unlocked.
    """

    message_id: UUID | None = None
    # The questions open when the message arrived. A classification answers
    # these and never a question asked later under the same message.
    questions_at_arrival: list[str] = Field(default_factory=list)
    intent_classified: bool = False
    framed: bool = False
    built: bool = False
    # A write this turn made outside a build: a clear, or an export the site
    # did not take.
    edited: bool = False
    verified: bool = False
    verification_dispatched: bool = False
    # A reply that did not match the turn's record is corrected once.
    contract_refused: bool = False
    # The EDA datasets this turn opened an analysis on.
    eda_datasets_opened: list[str] = Field(default_factory=list)
    # The EDA cut this turn exported, which the turn's case records.
    eda_export: EdaExport | None = None
    # Every enrichment answered under this message, in the order the workers
    # answered them. A reply reads it to say which set an analysis ran on.
    enrichment_runs: list[EnrichmentRun] = Field(default_factory=list)
    # Every url, DOI and PMID this turn's own reads retrieved. A reference the
    # reply cites is checked against it.
    retrieved_sources: list[str] = Field(default_factory=list)
    # The control sets this turn wrote. A reply that claims one is checked
    # against it.
    created_control_sets: list[CreatedControlSet] = Field(default_factory=list)
    # The workbench gene sets this turn saved, checked the same way. The
    # record belongs here, so a turn resumed after a park still holds it.
    created_gene_sets: list[CreatedGeneSet] = Field(default_factory=list)
    # The searches the steps this turn added run. The reply names each one.
    added_searches: list[AddedSearch] = Field(default_factory=list)
    # The questions the latest answer under this message closed.
    answered: AnsweredQuestions | None = None
    # The researcher answered a consult, or accepted a proposal, under this message.
    consulted: bool = False
    accepted_proposal: bool = False

    @property
    def changed_strategy(self) -> bool:
        """Whether this turn wrote to the strategy."""
        return self.built or self.edited

    @property
    def build_unverified(self) -> bool:
        """Whether this turn built and no pass checked the result."""
        return self.built and not (self.verified or self.verification_dispatched)

    def record_eda_dataset_opened(self, dataset_id: str) -> None:
        """Record the dataset this turn opened an analysis on, once."""
        if dataset_id not in self.eda_datasets_opened:
            self.eda_datasets_opened.append(dataset_id)

    def record_retrieved_source(self, reference: str) -> None:
        """Record one reference this turn retrieved, once."""
        if reference and reference not in self.retrieved_sources:
            self.retrieved_sources.append(reference)

    def record_control_set(self, control_set: CreatedControlSet) -> None:
        """Record one control set this turn wrote, once."""
        if control_set.id not in {held.id for held in self.created_control_sets}:
            self.created_control_sets.append(control_set)

    def record_gene_set(self, gene_set: CreatedGeneSet) -> None:
        """Record one workbench gene set this turn saved, once."""
        if gene_set.id not in {held.id for held in self.created_gene_sets}:
            self.created_gene_sets.append(gene_set)

    def record_added_searches(self, searches: Iterable[AddedSearch]) -> None:
        """Record each added step once, keyed by its step id."""
        held = {search.step_id for search in self.added_searches}
        self.added_searches.extend(s for s in searches if s.step_id not in held)

    def record_enrichment_runs(self, runs: Iterable[EnrichmentRun]) -> None:
        """Add each answered enrichment once, keyed by its task."""
        known = {run.task_id for run in self.enrichment_runs}
        for run in runs:
            if run.task_id in known:
                continue
            known.add(run.task_id)
            self.enrichment_runs.append(run)
