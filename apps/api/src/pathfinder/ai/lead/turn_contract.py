"""The Lead's typed reply, the record of the turn it answers - what it wrote
and what it retrieved - and the reconciliation that holds one against the
other."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.state import CreatedControlSet, EnrichmentRun
from pathfinder.ai.lead.contract_messages import (
    analysis_ran_on_another_set_message,
    blamed_the_site_message,
    claimed_change_message,
    control_set_not_written_message,
    eda_criterion_not_built_message,
    gene_set_not_saved_message,
    off_topic_essay_message,
    unfinished_work_message,
    unrecorded_question_message,
    unreported_change_message,
    unretrieved_source_message,
    unverified_build_message,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent_gate import (
    tools_the_turn_offers,
    turn_builds,
    turn_is_off_topic,
)
from pathfinder.ai.lead.ledger import blamed_the_site
from pathfinder.ai.lead.ledger_sections import BuildSection
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.lead.sub_agent_tools import TOOL_TO_PHASE_ROLE, LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    DroppedCriterion,
    eda_backed_drops,
)

LeadTurnState = Literal["await_user", "complete"]

# An out-of-scope reply is a redirect, and a redirect is two sentences.
OFF_TOPIC_REPLY_MAX_CHARS = 400
_CODE_FENCE = "```"

CONTRACT_HEADING = "This reply does not match what the turn did:"

# The tools the Lead calls to do the turn's work. ``build_strategy`` runs no
# sub-agent and is refused the same way the dispatches are.
DISPATCH_TOOLS: frozenset[str] = frozenset(TOOL_TO_PHASE_ROLE) | {"build_strategy"}

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


# An artifact the reply reports as saved. An offer to save one is an
# infinitive, and a listing says "saved control sets" with no words between.
_SAVED = r"\b(?:created|saved|built|made|added|stored)\s+.{1,40}?\b"
# A gene set that qualifies another noun names an analysis or a note.
_THE_SET_ITSELF = r"(?!\s+(?:enrichment|note))"
_SAVED_A_CONTROL_SET = re.compile(_SAVED + r"control sets?\b")
_SAVED_A_GENE_SET = re.compile(_SAVED + r"gene sets?\b" + _THE_SET_ITSELF)
_DENIED = re.compile(r"\b(?:not|never|no)\b|n't")
_CLAUSE_END = re.compile(r"[.!?;\n]")


def _claims_it_saved(prose: str, artifact: re.Pattern[str]) -> bool:
    """Whether this reply tells the user it saved that artifact."""
    return any(
        artifact.search(clause)
        for clause in _CLAUSE_END.split(prose.casefold())
        if not _DENIED.search(clause)
    )


def normalized_reference(value: str) -> str:
    """One comparable form of a url, a DOI or a PMID."""
    text = value.strip().casefold()
    for prefix in _REFERENCE_PREFIXES:
        text = text.removeprefix(prefix)
    return text.rstrip("/")


class CitedSource(CamelModel):
    """One reference a reply names, and where this turn read it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["record", "literature", "web"]
    label: str = Field(
        max_length=200,
        description=(
            "What the reader sees: the gene id and the site for a record, the "
            "title for a paper or a page."
        ),
    )
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None

    def references(self) -> list[str]:
        """Every identifier this source is checked by."""
        return [value for value in (self.url, self.doi, self.pmid) if value]


class LeadResponse(CamelModel):
    """The Lead's final user-facing turn output.

    ``prose`` is rendered to the user verbatim (no upstream/downstream
    translation). ``next_state`` tells the dispatcher whether the turn is
    paused waiting on the user (``await_user``) or fully resolved
    (``complete`` - typically after a successful verification).
    """

    prose: str = Field(
        max_length=4000,
        description=(
            "User-facing reply for this turn. Plain markdown. Do NOT "
            "include sub-agent log noise - synthesize from the Ledger."
        ),
    )
    next_state: LeadTurnState = "await_user"
    strategy_changed: bool = Field(
        description=(
            "True when this turn built, edited, deleted, cleared, or exported "
            "a step into the strategy. False when the strategy is as the turn "
            "found it. The runtime checks this against what the turn actually "
            "wrote."
        ),
    )
    asked_questions: list[OpenQuestion] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "One entry per question this reply asks the user, carrying the "
            "value you recommend for it and the dimension it decides. A "
            "question you ask in prose and leave out of here is one the next "
            "turn has to ask again."
        ),
    )
    analysed_gene_set_ids: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "The id of every gene set whose enrichment this reply reports on. "
            "An analysis that ran on a set other than the one the request "
            "named is reported under the id it actually ran on."
        ),
    )
    sources: list[CitedSource] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "One entry per reference this reply names: a gene record you read, "
            "a paper, or a page. Every url, DOI and PMID here must be one a "
            "read of THIS turn returned; a reference you did not retrieve is "
            "one the user cannot check."
        ),
    )


class TurnRecord(CamelModel):
    """What this turn did, as the reply must account for it."""

    model_config = ConfigDict(frozen=True)

    changed_strategy: bool
    build_unverified: bool
    build_outcome: BuildOutcome | None
    eda_criterion_pending: DroppedCriterion | None
    turn_builds: bool
    framed: bool
    off_topic: bool
    analysed: EnrichmentRun | None
    substituted: list[EnrichmentRun]
    last_phase_stop: PhaseStop | None
    refused_dispatches: tuple[str, ...]
    build_section: BuildSection
    retrieved_sources: tuple[str, ...]
    created_control_sets: tuple[CreatedControlSet, ...]
    created_gene_sets: tuple[CreatedGeneSet, ...]


MismatchKind = Literal[
    "unverified_build",
    "misreported_change",
    "unwritten_control_set",
    "unwritten_gene_set",
    "unbuilt_eda_criterion",
    "blamed_the_site",
    "unrecorded_question",
    "unfinished_work",
    "substituted_analysis",
    "off_topic_essay",
    "unretrieved_source",
]


class Mismatch(CamelModel):
    """One way the reply and the record disagree, and the sentence that says so."""

    model_config = ConfigDict(frozen=True)

    kind: MismatchKind
    sentence: str


def _pending_eda_criterion(deps: LeadDeps) -> DroppedCriterion | None:
    """The dropped EDA criterion this turn opened no analysis for, or None.

    An analysis the thread already holds open on that dataset counts: the
    filters and the export act on it.
    """
    opened = set(deps.state.turn_markers.eda_datasets_opened)
    analysis = deps.state.domain.open_eda_analysis
    if analysis is not None:
        opened.add(analysis.dataset_id)
    return next(
        (
            dropped
            for dropped in eda_backed_drops(deps.state.domain.operational_spec)
            if dropped.eda_dataset_id not in opened
        ),
        None,
    )


def _analysis_and_what_it_replaced(
    runs: Sequence[EnrichmentRun],
) -> tuple[EnrichmentRun | None, list[EnrichmentRun]]:
    """The enrichment this turn ran, and the failures it was reached around.

    Only a failure recorded before the run that succeeded, on another set, is
    a substitution.
    """
    ran_at = max((i for i, run in enumerate(runs) if run.succeeded), default=-1)
    if ran_at < 0:
        return None, []
    analysed = runs[ran_at]
    return analysed, [
        run
        for run in runs[:ran_at]
        if not run.succeeded and run.gene_set_id != analysed.gene_set_id
    ]


def _refused_dispatches(ctx: RunContext[LeadDeps]) -> tuple[str, ...]:
    """The dispatch tools this run refused and never ran again.

    The run drops a tool from its retry record as soon as one call of it
    returns, so what is left is work the turn asked for and never did. A tool
    this turn never offered is a name the run did not know, not work it owes.
    """
    offered = tools_the_turn_offers(ctx.deps, DISPATCH_TOOLS)
    return tuple(sorted(name for name in ctx.retries if name in offered))


def turn_record(ctx: RunContext[LeadDeps]) -> TurnRecord:
    """Everything the contract reads about the turn this reply answers."""
    deps = ctx.deps
    markers = deps.state.turn_markers
    analysed, substituted = _analysis_and_what_it_replaced(markers.enrichment_runs)
    return TurnRecord(
        changed_strategy=markers.changed_strategy,
        build_unverified=markers.build_unverified,
        build_outcome=deps.state.domain.last_build_outcome,
        eda_criterion_pending=_pending_eda_criterion(deps),
        turn_builds=turn_builds(deps),
        framed=markers.framed,
        off_topic=turn_is_off_topic(deps),
        analysed=analysed,
        substituted=substituted,
        last_phase_stop=deps.last_phase_stop,
        refused_dispatches=_refused_dispatches(ctx),
        build_section=derive_ledger(deps.state, deps.intent).build,
        retrieved_sources=tuple(markers.retrieved_sources),
        created_control_sets=tuple(markers.created_control_sets),
        created_gene_sets=tuple(markers.created_gene_sets),
    )


def _unverified_build(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that built and reached no check answers for work nothing saw."""
    del report
    if not record.build_unverified:
        return None
    return unverified_build_message(record.build_outcome)


def _misreported_change(report: LeadResponse, record: TurnRecord) -> str | None:
    """The turn's markers are the record of what the strategy holds now."""
    if report.strategy_changed == record.changed_strategy:
        return None
    if record.changed_strategy:
        return unreported_change_message()
    return claimed_change_message(record.build_outcome)


def _unwritten_control_set(report: LeadResponse, record: TurnRecord) -> str | None:
    """A durable artifact the reply reports is one this turn wrote."""
    if record.created_control_sets or not _claims_it_saved(
        report.prose, _SAVED_A_CONTROL_SET
    ):
        return None
    return control_set_not_written_message(record.created_gene_sets)


def _unwritten_gene_set(report: LeadResponse, record: TurnRecord) -> str | None:
    """The same rule for the other artifact a reply can put the wrong name on."""
    if record.created_gene_sets or not _claims_it_saved(
        report.prose, _SAVED_A_GENE_SET
    ):
        return None
    return gene_set_not_saved_message(record.created_control_sets)


def _unbuilt_eda_criterion(report: LeadResponse, record: TurnRecord) -> str | None:
    """Only the EDA tools build a dropped EDA-backed criterion."""
    del report
    if not record.turn_builds or record.eda_criterion_pending is None:
        return None
    return eda_criterion_not_built_message(record.eda_criterion_pending)


def _blamed_the_site(report: LeadResponse, record: TurnRecord) -> str | None:
    """A pass that ran out of calls is this turn's own limit."""
    blame = blamed_the_site(report.prose, build=record.build_section)
    if blame is None:
        return None
    return blamed_the_site_message(blame, record.last_phase_stop)


def _unrecorded_question(report: LeadResponse, record: TurnRecord) -> str | None:
    """The next turn binds what the reply recorded, not what its prose asks."""
    if not record.framed or report.next_state != "await_user":
        return None
    if report.asked_questions or "?" not in report.prose:
        return None
    return unrecorded_question_message()


def _unfinished_work(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn whose work did not run ends by asking the user, not by promising.

    The state the reply claims decides nothing: work that did not run is undone
    whether the reply waits on the user or calls the turn resolved.
    """
    if record.changed_strategy or report.asked_questions:
        return None
    if not record.refused_dispatches and record.last_phase_stop is None:
        return None
    return unfinished_work_message(record.refused_dispatches, record.last_phase_stop)


def _substituted_analysis(report: LeadResponse, record: TurnRecord) -> str | None:
    """An analysis reached around a failure is reported under its own set."""
    analysed = record.analysed
    if analysed is None or not record.substituted:
        return None
    if analysed.gene_set_id in report.analysed_gene_set_ids:
        return None
    return analysis_ran_on_another_set_message(analysed, record.substituted)


def _off_topic_essay(report: LeadResponse, record: TurnRecord) -> str | None:
    """An out-of-scope turn reaches no tool, so the prose is the only cost."""
    if not record.off_topic:
        return None
    prose = report.prose
    if _CODE_FENCE not in prose and len(prose) <= OFF_TOPIC_REPLY_MAX_CHARS:
        return None
    return off_topic_essay_message(OFF_TOPIC_REPLY_MAX_CHARS)


def _unretrieved_source(report: LeadResponse, record: TurnRecord) -> str | None:
    """A reference the reply lists is one a read of this turn returned."""
    retrieved = {normalized_reference(found) for found in record.retrieved_sources}
    absent = [
        reference
        for source in report.sources
        for reference in source.references()
        if normalized_reference(reference) not in retrieved
    ]
    if not absent:
        return None
    return unretrieved_source_message(absent)


_RULES: tuple[
    tuple[MismatchKind, Callable[[LeadResponse, TurnRecord], str | None]], ...
] = (
    ("unverified_build", _unverified_build),
    ("misreported_change", _misreported_change),
    ("unwritten_control_set", _unwritten_control_set),
    ("unwritten_gene_set", _unwritten_gene_set),
    ("unbuilt_eda_criterion", _unbuilt_eda_criterion),
    ("blamed_the_site", _blamed_the_site),
    ("unrecorded_question", _unrecorded_question),
    ("unfinished_work", _unfinished_work),
    ("substituted_analysis", _substituted_analysis),
    ("off_topic_essay", _off_topic_essay),
    ("unretrieved_source", _unretrieved_source),
)


def reconcile(report: LeadResponse, record: TurnRecord) -> list[Mismatch]:
    """Every way this reply disagrees with the turn it answers, in rule order."""
    found: list[Mismatch] = []
    for kind, rule in _RULES:
        sentence = rule(report, record)
        if sentence is not None:
            found.append(Mismatch(kind=kind, sentence=sentence))
    return found


def hold_the_turn_contract(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse the first answer of a turn that does not match the turn's record.

    One correction carries every mismatch, and it is asked once per turn, so a
    second answer reaches the user whatever it says.
    """
    if not isinstance(output, LeadResponse):
        return output
    markers = ctx.deps.state.turn_markers
    if markers.contract_refused:
        return output
    mismatches = reconcile(output, turn_record(ctx))
    if not mismatches:
        return output
    markers.contract_refused = True
    raise ModelRetry(
        "\n\n".join([CONTRACT_HEADING, *(m.sentence for m in mismatches)]),
    )
