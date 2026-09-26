"""The Lead's typed reply and the reconciliation that holds it against the
record of the turn it answers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.turn_records import normalized_reference
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS
from pathfinder.ai.lead.contract_messages import (
    blamed_the_site_message,
    claimed_change_message,
    claimed_frame_message,
    control_set_not_written_message,
    counted_in_the_wrong_unit_message,
    eda_criterion_not_built_message,
    gene_set_not_saved_message,
    machine_words_message,
    misnamed_deletion_message,
    off_topic_essay_message,
    unbacked_evidence_message,
    unfinished_work_message,
    unnamed_record_organism_message,
    unrecorded_offer_message,
    unrecorded_question_message,
    unreported_change_message,
    unreported_requirement_message,
    unretrieved_source_message,
    unstated_qualifier_message,
    unverified_build_message,
)
from pathfinder.ai.lead.count_claims import misstated_count_message, misstated_counts
from pathfinder.ai.lead.deleted_steps import misnamed_removal
from pathfinder.ai.lead.evidence_claims import (
    control_claims,
    sample_claims,
    unbacked_claims,
    unbacked_sample_claims,
)
from pathfinder.ai.lead.ledger import blamed_the_site
from pathfinder.ai.lead.reply_claims import (
    CLAIMED_A_FRAME,
    SAVED_A_CONTROL_SET,
    SAVED_A_GENE_SET,
    claims,
    counts_named_as,
    ends_with_a_question,
    machine_words,
    names_an_organism,
)
from pathfinder.ai.lead.search_reasons import unnamed_search
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_record import TurnRecord, turn_record
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.evidence import SourceReference
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.step_rationale import names_the_phrase

LeadTurnState = Literal["await_user", "complete"]

# An out-of-scope reply is a redirect, and a redirect is two sentences.
OFF_TOPIC_REPLY_MAX_CHARS = 400
_CODE_FENCE = "```"

CONTRACT_HEADING = "This reply does not match what the turn did:"


class LeadResponse(CamelModel):
    """The Lead's final user-facing turn output.

    ``prose`` is rendered to the user verbatim (no upstream/downstream
    translation). ``next_state`` tells the dispatcher whether the turn is
    paused waiting on the user (``await_user``) or fully resolved
    (``complete`` - typically after a successful verification).
    """

    prose: str = Field(
        max_length=PROSE_MAX_CHARS,
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
    sources: list[SourceReference] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "One entry per reference this reply names: a gene record you read, "
            "a paper, or a page. Every url, DOI and PMID here must be one a "
            "read of THIS turn returned; a reference you did not retrieve is "
            "one the user cannot check."
        ),
    )


MismatchKind = Literal[
    "unverified_build",
    "misreported_change",
    "claimed_frame",
    "unwritten_control_set",
    "unwritten_gene_set",
    "unbuilt_eda_criterion",
    "blamed_the_site",
    "unrecorded_question",
    "unfinished_work",
    "machine_words",
    "off_topic_essay",
    "unretrieved_source",
    "unnamed_search",
    "unnamed_record_organism",
    "unstated_qualifier",
    "unreported_requirement",
    "unbacked_evidence",
    "misnamed_deletion",
    "counted_in_the_wrong_unit",
    "misstated_count",
]


class Mismatch(CamelModel):
    """One way the reply and the record disagree, and the sentence that says so."""

    model_config = ConfigDict(frozen=True)

    kind: MismatchKind
    sentence: str


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


def _claimed_frame(report: LeadResponse, record: TurnRecord) -> str | None:
    """A criterion the reply reports as framed is one the spec diff states."""
    diff = record.frame_diff
    if diff is None or diff.added_count or diff.changed_count:
        return None
    if not claims(report.prose, CLAIMED_A_FRAME):
        return None
    return claimed_frame_message(diff)


def _unwritten_control_set(report: LeadResponse, record: TurnRecord) -> str | None:
    """A durable artifact the reply reports is one this turn wrote."""
    if record.created_control_sets or not claims(report.prose, SAVED_A_CONTROL_SET):
        return None
    return control_set_not_written_message(record.created_gene_sets)


def _unwritten_gene_set(report: LeadResponse, record: TurnRecord) -> str | None:
    """The same rule for the other artifact a reply can put the wrong name on."""
    if record.created_gene_sets or not claims(report.prose, SAVED_A_GENE_SET):
        return None
    return gene_set_not_saved_message(record.created_control_sets)


def _unbuilt_eda_criterion(report: LeadResponse, record: TurnRecord) -> str | None:
    """Only the EDA tools build a criterion waiting for its analysis."""
    del report
    if not record.turn_builds or record.eda_criterion_pending is None:
        return None
    return eda_criterion_not_built_message(record.eda_criterion_pending)


def _blamed_the_site(report: LeadResponse, record: TurnRecord) -> str | None:
    """A pass that ran out of calls is this turn's own limit."""
    blame = blamed_the_site(
        report.prose,
        build=record.build_section,
        verification=record.verification_section,
    )
    if blame is None:
        return None
    return blamed_the_site_message(blame, record.last_phase_stop)


def _unrecorded_question(report: LeadResponse, record: TurnRecord) -> str | None:
    """The next turn binds what the reply recorded, not what its prose asks.

    A reply that ends on a question is an offer whatever the turn did, so it
    stands only beside a recorded question or a card the researcher answered.
    """
    if report.asked_questions or record.answered_a_card or record.ends_on_a_card:
        return None
    if ends_with_a_question(report.prose):
        return unrecorded_offer_message()
    if record.framed and report.next_state == "await_user" and "?" in report.prose:
        return unrecorded_question_message()
    return None


def _unfinished_work(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn whose work did not run ends by asking the user, not by promising.

    The state the reply claims decides nothing: work that did not run is undone
    whether the reply waits on the user or calls the turn resolved. A card is a
    question to the user.
    """
    if record.changed_strategy or report.asked_questions or record.ends_on_a_card:
        return None
    if not record.refused_dispatches and record.last_phase_stop is None:
        return None
    return unfinished_work_message(record.refused_dispatches, record.last_phase_stop)


def _machine_words(report: LeadResponse, record: TurnRecord) -> str | None:
    """A reply about work that did not run says so in the user's own words.

    A tool name, a minted step id and an error code name nothing the
    researcher holds, so the reply that reports a failure carries none of them.
    """
    if not _work_did_not_run(record):
        return None
    found = machine_words(report.prose)
    if not found:
        return None
    return machine_words_message(found)


def _work_did_not_run(record: TurnRecord) -> bool:
    """Whether a pass of this turn was refused, stopped, or lost a step."""
    return bool(
        record.refused_dispatches
        or record.last_phase_stop is not None
        or record.build_section.failed_count
    )


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


def _unnamed_search(report: LeadResponse, record: TurnRecord) -> str | None:
    """A step this turn added is named by its search, beside its reason."""
    return unnamed_search(report.prose, record.added_searches)


def _unnamed_record_organism(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that moved the records to another organism names that organism."""
    outcome = record.build_outcome
    change = None if outcome is None else outcome.organism_change
    if not record.changed_strategy or change is None:
        return None
    if all(names_an_organism(report.prose, organism) for organism in change.records):
        return None
    return unnamed_record_organism_message(change)


def _unstated_qualifier(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that framed or wrote a requirement no search states says so."""
    if not (record.framed or record.changed_strategy):
        return None
    silent = [
        word
        for word in record.unexpressed_qualifiers
        if not names_the_phrase(report.prose, word)
    ]
    return unstated_qualifier_message(silent) if silent else None


def _unreported_requirement(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that checked the strategy names each requirement the check found
    unmet or unexpressed. A word the qualifier rule already asks for is its own."""
    qualifier_rule = record.framed or record.changed_strategy
    silent = [
        row
        for row in record.requirements_to_report
        if not names_the_phrase(report.prose, row.text)
        and not (qualifier_rule and row.text in record.unexpressed_qualifiers)
    ]
    return unreported_requirement_message(silent) if silent else None


def _unbacked_evidence(report: LeadResponse, record: TurnRecord) -> str | None:
    """A control result or a sampled-gene count the reply states is one this
    turn or its last check holds."""
    found = [
        *unbacked_claims(control_claims(report.prose), record.control_results),
        *unbacked_sample_claims(sample_claims(report.prose), record.sampled_genes),
    ]
    return unbacked_evidence_message(found) if found else None


def _misnamed_deletion(report: LeadResponse, record: TurnRecord) -> str | None:
    """A removal the reply claims names a step this turn deleted."""
    if not record.deleted_steps:
        return None
    claimed = misnamed_removal(
        report.prose, record.deleted_steps, record.standing_steps
    )
    if claimed is None:
        return None
    return misnamed_deletion_message(claimed, record.deleted_steps)


def _counted_in_the_wrong_unit(report: LeadResponse, record: TurnRecord) -> str | None:
    """A step count is named in the noun the site counts the strategy in."""
    noun = counted_noun(record.record_type)
    if not record.record_type or noun == record.record_type:
        return None
    held = set(record.step_counts)
    named = counts_named_as(report.prose, record.record_type, instead_of=noun)
    wrong = [count for count in dict.fromkeys(named) if count in held]
    if not wrong:
        return None
    return counted_in_the_wrong_unit_message(record.record_type, noun, wrong)


def _misstated_count(report: LeadResponse, record: TurnRecord) -> str | None:
    """A count the reply states for the strategy is one a step of it holds, or
    held when the message arrived."""
    if not record.record_type or not record.step_counts:
        return None
    noun = counted_noun(record.record_type)
    stated = misstated_counts(
        report.prose,
        noun=noun,
        record_type=record.record_type,
        held=(*record.step_counts, *record.counts_at_arrival),
    )
    return misstated_count_message(noun, stated, record.step_counts) if stated else None


_RULES: tuple[
    tuple[MismatchKind, Callable[[LeadResponse, TurnRecord], str | None]], ...
] = (
    ("unverified_build", _unverified_build),
    ("misreported_change", _misreported_change),
    ("claimed_frame", _claimed_frame),
    ("unwritten_control_set", _unwritten_control_set),
    ("unwritten_gene_set", _unwritten_gene_set),
    ("unbuilt_eda_criterion", _unbuilt_eda_criterion),
    ("blamed_the_site", _blamed_the_site),
    ("unrecorded_question", _unrecorded_question),
    ("unfinished_work", _unfinished_work),
    ("machine_words", _machine_words),
    ("off_topic_essay", _off_topic_essay),
    ("unretrieved_source", _unretrieved_source),
    ("unnamed_search", _unnamed_search),
    ("unnamed_record_organism", _unnamed_record_organism),
    ("unstated_qualifier", _unstated_qualifier),
    ("unreported_requirement", _unreported_requirement),
    ("unbacked_evidence", _unbacked_evidence),
    ("misnamed_deletion", _misnamed_deletion),
    ("counted_in_the_wrong_unit", _counted_in_the_wrong_unit),
    ("misstated_count", _misstated_count),
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
    raise ModelRetry(correction_for(mismatches))


def correction_for(mismatches: Sequence[Mismatch]) -> str:
    """The one correction that lists every mismatch under one heading."""
    return "\n\n".join([CONTRACT_HEADING, *(m.sentence for m in mismatches)])
