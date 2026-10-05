"""The small records one turn keeps: what it answered, emptied, ran and wrote."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.domain.comparison_facts import ComparisonFact
from pathfinder.domain.constraint_check import ConstraintCheck
from pathfinder.domain.eda_thread import EdaExport
from pathfinder.domain.evidence import ColumnFit, ControlTestEvidence
from pathfinder.domain.last_change import LastChange
from pathfinder.domain.membership_facts import MembershipFact
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.step_words import AddedSearch

# What a written reference carries before the identifier itself.
_REFERENCE_PREFIXES = (
    "https://",
    "http://",
    "www.",
    "doi.org/",
    "dx.doi.org/",
    "doi:",
    "pmid:",
    "pubmed.ncbi.nlm.nih.gov/",
)


def normalized_reference(value: str) -> str:
    """One comparable form of a url, a DOI or a PMID."""
    text = value.strip().casefold()
    for prefix in _REFERENCE_PREFIXES:
        text = text.removeprefix(prefix)
    return text.rstrip("/")


class NamedStep(CamelModel):
    """A step as a reply names it: its title and its search."""

    model_config = ConfigDict(frozen=True)

    title: str
    search_name: str | None = None

    def described(self) -> str:
        """The step as a correction names it: the title, then the search."""
        if self.search_name is None:
            return f"'{self.title}'"
        return f"'{self.title}' ({self.search_name})"


class ReadRecord(CamelModel):
    """A record a read of this turn returned: its id, its page and what it states."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    url: str
    product: str = ""
    organism: str = ""
    gene_name: str = ""
    chromosome: str = ""
    # The ortholog ids and organisms of the one organism the read asked for.
    # The first rows of the ortholog table are no fact a researcher checks.
    asked_orthologs: list[str] = Field(default_factory=list)

    def words(self) -> list[str]:
        """The record's other words, its chromosome named as one."""
        chromosome = f"chromosome {self.chromosome}" if self.chromosome else ""
        return [t for t in (self.gene_name, chromosome, *self.asked_orthologs) if t]


class ZeroResultStep(CamelModel):
    """A search that came back empty on some build of this thread."""

    search_name: str
    criterion_text: str = ""


# What filed the controls: a control test, a scored comparison or a sweep.
ControlTestOrigin = Literal["control_test", "scored_comparison", "sweep"]


class ControlTestRun(CamelModel):
    """One control result this turn read, as its source filed the controls."""

    model_config = ConfigDict(frozen=True)

    tool_call_id: str
    evidence: ControlTestEvidence
    origin: ControlTestOrigin = "control_test"


class CreatedControlSet(CamelModel):
    """A control set one turn wrote, as a reply that names it must read."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str


class RefusedCall(CamelModel):
    """A call a tool refused, by the digest of its arguments."""

    tool_name: str
    arguments: str
    refusal: str
    # The same call came back once and failed without running.
    sent_again: bool = False


class ControlTestTarget(CamelModel):
    """One saved control set on one built step."""

    model_config = ConfigDict(frozen=True)

    wdk_step_id: int
    control_set_id: str


class AnsweredQuestions(CamelModel):
    """The questions one answer closed, and the words of that answer."""

    questions: list[OpenQuestion]
    answer: str
    # A card answers questions a pass asked under this same message.
    on_card: bool = False


class CountsAtArrival(CamelModel):
    """The strategy as a message found it: its root and each step's count."""

    model_config = ConfigDict(frozen=True)

    root_id: str = ""
    counts: dict[str, int] = Field(default_factory=dict)


class ChangeAtArrival(CamelModel):
    """The tree a message found, with its counts, and the change that made it."""

    model_config = ConfigDict(frozen=True)

    tree: StrategyAst | None = None
    change: LastChange | None = None


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
    # A catalog lookup of this turn ran, so a reply may say a search is absent.
    catalog_looked_up: bool = False
    framed: bool = False
    built: bool = False
    # A write this turn made outside a build: a clear, or an export the site
    # did not take.
    edited: bool = False
    verified: bool = False
    verification_dispatched: bool = False
    # The last check of this turn has no digest: it stopped, raised or still runs.
    verification_stopped: bool = False
    # A reply that did not match the turn's record is corrected once.
    contract_refused: bool = False
    # The EDA datasets this turn opened an analysis on.
    eda_datasets_opened: list[str] = Field(default_factory=list)
    # The EDA cut this turn exported, which the turn's case records.
    eda_export: EdaExport | None = None
    # Every control result this turn read, in the order each one answered.
    control_tests: list[ControlTestRun] = Field(default_factory=list)
    # Every column a check of this turn read, the latest read of each.
    column_fits: list[ColumnFit] = Field(default_factory=list)
    # The study-step checks this turn computed, the latest read of each step.
    study_checks: dict[str, list[ConstraintCheck]] = Field(default_factory=dict)
    # The strategy as the message found it. Every count before an edit of
    # this turn is read from it.
    at_arrival: CountsAtArrival | None = None
    # The tree the message found and the thread's last change before it.
    change_at_arrival: ChangeAtArrival | None = None
    # The genes whose record each check of this turn read, by check id.
    records_read: dict[str, list[str]] = Field(default_factory=dict)
    # The genes a sample of this turn returned, whose records a check may read.
    sampled_gene_ids: list[str] = Field(default_factory=list)
    # The gene ids each listing or sample of this turn returned, by WDK step,
    # once each and in the order they came.
    listings: dict[int, list[str]] = Field(default_factory=dict)
    # The records this turn's reads returned, once each by id.
    records_retrieved: list[ReadRecord] = Field(default_factory=list)
    # The genes the message names that the classification gate resolved.
    resolved_genes: list[ReadRecord] = Field(default_factory=list)
    # The counts each completed comparison of this turn returned, in order.
    comparisons: list[ComparisonFact] = Field(default_factory=list)
    # Which of the asked genes each membership check of this turn found held.
    memberships: list[MembershipFact] = Field(default_factory=list)
    # The checks whose digest was corrected once for its control results.
    refused_digests: list[str] = Field(default_factory=list)
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
    # The requirements this message added to the thread's record.
    requirements_added: list[Constraint] = Field(default_factory=list)
    # The requirements a framing pass of this message found no search states.
    unstated_requirements: list[str] = Field(default_factory=list)
    # The steps this turn deleted, as they stood before the delete.
    deleted_steps: list[NamedStep] = Field(default_factory=list)
    # Why the edit this turn dispatched could not be bound, once no pass may
    # retry it. The facts show it.
    unbound_edit: str = ""
    # The steps each delete card listed, by the card's tool call id.
    delete_cards: dict[str, list[str]] = Field(default_factory=dict)
    # The questions the latest answer under this message closed.
    answered: AnsweredQuestions | None = None
    # The researcher answered a consult, or accepted a proposal, under this message.
    consulted: bool = False
    # The consult card this message last had an answer to, and the one whose
    # answer the latest classification read, by tool call id.
    answered_card: str = ""
    classified_card: str = ""
    accepted_proposal: bool = False
    # The calls refused since the last call that ran; a call that runs clears them.
    refused_calls: list[RefusedCall] = Field(default_factory=list)
    # The control tests asked again under this message, and answered from the first.
    control_tests_asked_again: list[ControlTestTarget] = Field(default_factory=list)

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

    def retrieved_as(self, reference: str) -> str | None:
        """The form a read of this turn returned the reference in, else None."""
        wanted = normalized_reference(reference)
        return next(
            (
                found
                for found in self.retrieved_sources
                if normalized_reference(found) == wanted
            ),
            None,
        )

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

    def record_column_fits(self, fits: Iterable[ColumnFit]) -> None:
        """Keep one fit per step and column, the latest read."""
        read = {fit.column_key: fit for fit in self.column_fits}
        read.update({fit.column_key: fit for fit in fits})
        self.column_fits = list(read.values())

    def record_arrival(
        self, root_id: str | None, counts: Mapping[str, int | None]
    ) -> None:
        """Keep the strategy as the message found it, once per message."""
        if self.at_arrival is not None:
            return
        self.at_arrival = CountsAtArrival(
            root_id=root_id or "",
            counts={step: n for step, n in counts.items() if n is not None},
        )

    def record_change_at_arrival(
        self, tree: StrategyAst | None, change: LastChange | None
    ) -> None:
        """Keep the tree the message found and its last change, once per message."""
        if self.change_at_arrival is None:
            self.change_at_arrival = ChangeAtArrival(tree=tree, change=change)

    def _held_at_arrival(self, step_id: str) -> int | None:
        """The count the message found for the step, or for the step an export
        of this turn put it in the place of. A step the turn created has none."""
        if not self.changed_strategy or self.at_arrival is None:
            return None
        export = self.eda_export
        replaced = (
            export.replaced_step_id
            if export is not None and export.step_id == step_id
            else None
        )
        return self.at_arrival.counts.get(replaced or step_id)

    def count_before(self, step_id: str, now: int | None) -> int | None:
        """The count the step held when the message arrived, when this turn's
        writes moved it."""
        held = self._held_at_arrival(step_id)
        return None if held == now else held

    def root_count_before(self) -> int | None:
        """The count of the root the message found, once this turn wrote."""
        if self.at_arrival is None:
            return None
        return self._held_at_arrival(self.at_arrival.root_id)

    def record_listed_genes(self, wdk_step_id: int, gene_ids: Iterable[str]) -> None:
        """Keep each gene id a listing of the step returned, once."""
        held = self.listings.setdefault(wdk_step_id, [])
        held.extend(dict.fromkeys(g for g in gene_ids if g not in held))

    def listed_from(self, gene_id: str) -> int | None:
        """The first WDK step whose listing returned the gene id, or None."""
        return next(
            (step for step, genes in self.listings.items() if gene_id in genes), None
        )

    def record_read(self, record: ReadRecord) -> None:
        """Record one record a read returned, once, and its page as a source."""
        self.record_retrieved_source(record.url)
        held = {read.record_id for read in self.records_retrieved}
        if record.record_id not in held:
            self.records_retrieved.append(record)

    def record_resolved_genes(self, records: Iterable[ReadRecord]) -> None:
        """Record each gene the gate resolved, once."""
        held = {gene.record_id for gene in self.resolved_genes}
        self.resolved_genes.extend(r for r in records if r.record_id not in held)

    def record_comparison(self, comparison: ComparisonFact) -> None:
        """Keep the counts one completed comparison returned."""
        self.comparisons.append(comparison)

    def record_membership(self, membership: MembershipFact) -> None:
        """Keep which of the asked genes one membership check found held."""
        self.memberships.append(membership)

    def record_sampled_genes(self, gene_ids: Iterable[str]) -> None:
        """Record each gene a sample returned, once."""
        self.sampled_gene_ids.extend(
            dict.fromkeys(g for g in gene_ids if g not in self.sampled_gene_ids)
        )

    def control_gene_ids(self) -> frozenset[str]:
        """Every control id a control result of this turn filed."""
        return frozenset(
            gene_id
            for run in self.control_tests
            for filed in (run.evidence.positive, run.evidence.negative)
            if filed is not None
            for gene_id in (*filed.returned, *filed.not_returned)
        )

    def record_control_tests(self, runs: Iterable[ControlTestRun]) -> None:
        """Add each control test once, keyed by its tool call."""
        held = {run.tool_call_id for run in self.control_tests}
        for run in runs:
            if run.tool_call_id not in held:
                held.add(run.tool_call_id)
                self.control_tests.append(run)
