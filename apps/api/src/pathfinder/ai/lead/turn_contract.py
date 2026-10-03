"""The Lead's typed reply and the reconciliation that holds it against the
record of the turn it answers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, REPLY_REFERENCES
from pathfinder.ai.lead.contract_messages import (
    blamed_the_site_message,
    claimed_change_message,
    claimed_frame_message,
    eda_criterion_not_built_message,
    failed_check_message,
    off_topic_essay_message,
    unclassified_turn_message,
    unfinished_work_message,
    unmade_change_message,
    unnamed_record_organism_message,
    unrecorded_offer_message,
    unrendered_prose_message,
    unreported_change_message,
    unsaved_controls_message,
    unverified_build_message,
)
from pathfinder.ai.lead.ledger import blamed_the_site
from pathfinder.ai.lead.reply_claims import (
    CLAIMED_A_FRAME,
    claims,
    denies,
    ends_with_a_question,
    names_an_organism,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_record import TurnRecord, turn_record
from pathfinder.ai.lead.verdict_claims import open_value_in_prose, unstated_stop
from pathfinder.domain.reply_references import (
    prose_faults,
    render_reply,
    unheld_references,
)
from pathfinder.domain.strategy.questions import AskedQuestion

LeadTurnState = Literal["await_user", "complete"]

# An out-of-scope reply is a redirect, and a redirect is two sentences.
OFF_TOPIC_REPLY_MAX_CHARS = 400
_CODE_FENCE = "```"

CONTRACT_HEADING = "This reply does not match what the turn did:"


class LeadResponse(CamelModel):
    """The Lead's final reply. ``prose`` holds references the emitter renders
    from the turn's facts; ``next_state`` says whether the turn waits on the
    user."""

    prose: str = Field(
        max_length=PROSE_MAX_CHARS,
        description=(
            f"User-facing reply for this turn. Plain markdown. {REPLY_REFERENCES} "
            "Do NOT include sub-agent log noise - synthesize from the Ledger."
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
    asked_questions: list[AskedQuestion] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "One entry per question this reply asks the user, carrying the "
            "value you recommend for it and the dimension it decides. A "
            "question you ask in prose and leave out of here is one the next "
            "turn has to ask again."
        ),
    )


MismatchKind = Literal[
    "unverified_build",
    "misreported_change",
    "claimed_frame",
    "unbuilt_eda_criterion",
    "blamed_the_site",
    "open_value_in_prose",
    "unrecorded_question",
    "unfinished_work",
    "stopped_check",
    "unclassified_turn",
    "unsaved_controls",
    "off_topic_essay",
    "unnamed_record_organism",
    "unrendered_prose",
    "failed_check",
    "unmade_change",
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
    return unverified_build_message(record.build_outcome, record.facts.root_count)


def _misreported_change(report: LeadResponse, record: TurnRecord) -> str | None:
    """The turn's markers are the record of what the strategy holds now."""
    if report.strategy_changed == record.changed_strategy:
        return None
    if record.changed_strategy:
        return unreported_change_message(record.build_outcome, record.facts)
    return claimed_change_message(record.build_outcome, record.facts.root_count)


def _claimed_frame(report: LeadResponse, record: TurnRecord) -> str | None:
    """A criterion the reply reports as framed is one the spec diff states."""
    diff = record.frame_diff
    if diff is None or diff.added_count or diff.changed_count:
        return None
    if not claims(report.prose, CLAIMED_A_FRAME):
        return None
    return claimed_frame_message(diff)


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


def _open_value_in_prose(report: LeadResponse, record: TurnRecord) -> str | None:
    """A value the frame leaves open is asked on the question card."""
    del report
    return open_value_in_prose(record)


def _unrecorded_question(report: LeadResponse, record: TurnRecord) -> str | None:
    """The next turn binds what the reply recorded, not what its prose asks.

    A reply that ends on a question is an offer whatever the turn did, so it
    stands only beside a recorded question or a card the researcher answered.
    A value the frame leaves open is the question card's rule.
    """
    if report.asked_questions or record.answered_a_card or record.ends_on_a_card:
        return None
    if record.frame_open_questions:
        return None
    if ends_with_a_question(report.prose):
        return unrecorded_offer_message()
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


def _stopped_check(report: LeadResponse, record: TurnRecord) -> str | None:
    """A check that stopped recorded no verdict, so the reply says it stopped."""
    return unstated_stop(report.prose, record)


def _unclassified_turn(report: LeadResponse, record: TurnRecord) -> str | None:
    """A message is answered after its classification is accepted.

    A card answer, a typed acceptance and a turn that re-enters a parked call
    answer something the conversation holds, not the message's own request.
    """
    del report
    refused = record.refused_classification
    if refused is None or record.answered_a_card or record.ends_on_a_card:
        return None
    if record.resumes_parked_call:
        return None
    return unclassified_turn_message(refused.sentence)


def _unsaved_controls(report: LeadResponse, record: TurnRecord) -> str | None:
    """Controls the message names are saved as a control set, or asked about."""
    named = record.named_controls
    if named is None or not (named.positive_ids or named.negative_ids):
        return None
    if record.created_control_sets:
        return None
    if report.asked_questions or record.ends_on_a_card:
        return None
    return unsaved_controls_message(len(named.positive_ids), len(named.negative_ids))


def _off_topic_essay(report: LeadResponse, record: TurnRecord) -> str | None:
    """An out-of-scope turn reaches no tool, so the prose is the only cost."""
    if not record.off_topic:
        return None
    prose = report.prose
    if _CODE_FENCE not in prose and len(prose) <= OFF_TOPIC_REPLY_MAX_CHARS:
        return None
    return off_topic_essay_message(OFF_TOPIC_REPLY_MAX_CHARS)


def _unnamed_record_organism(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that moved the records to another organism names that organism."""
    outcome = record.build_outcome
    change = None if outcome is None else outcome.organism_change
    if not record.changed_strategy or change is None:
        return None
    if all(names_an_organism(report.prose, organism) for organism in change.records):
        return None
    return unnamed_record_organism_message(change)


def _failed_check(report: LeadResponse, record: TurnRecord) -> str | None:
    """A check that failed on the strategy as it stands is stated or asked about."""
    digest = record.verification_section.digest
    if digest is None or digest.success:
        return None
    if report.asked_questions or record.ends_on_a_card:
        return None
    if ends_with_a_question(report.prose) or digest.failure_stated_in(report.prose):
        return None
    return failed_check_message(digest.reason)


def _unmade_change(report: LeadResponse, record: TurnRecord) -> str | None:
    """A change an edit asks for is made, raised on a card, or refused in the reply."""
    asked = [*record.withdrawn_values, *record.stated_values]
    if not asked or record.changed_strategy or record.ends_on_a_card:
        return None
    if report.asked_questions or record.facts.refusal:
        return None
    if record.refused_dispatches or record.last_phase_stop is not None:
        return None
    if all(denies(report.prose, value) for value in asked):
        return None
    return unmade_change_message(record.withdrawn_values, record.stated_values)


_RULES: tuple[
    tuple[MismatchKind, Callable[[LeadResponse, TurnRecord], str | None]], ...
] = (
    ("unverified_build", _unverified_build),
    ("misreported_change", _misreported_change),
    ("claimed_frame", _claimed_frame),
    ("unbuilt_eda_criterion", _unbuilt_eda_criterion),
    ("blamed_the_site", _blamed_the_site),
    ("open_value_in_prose", _open_value_in_prose),
    ("unrecorded_question", _unrecorded_question),
    ("unfinished_work", _unfinished_work),
    ("stopped_check", _stopped_check),
    ("unclassified_turn", _unclassified_turn),
    ("unsaved_controls", _unsaved_controls),
    ("off_topic_essay", _off_topic_essay),
    ("unnamed_record_organism", _unnamed_record_organism),
    ("failed_check", _failed_check),
    ("unmade_change", _unmade_change),
)


def _as_read(report: LeadResponse, record: TurnRecord) -> LeadResponse:
    """The reply as the researcher reads it, once every reference renders."""
    if unheld_references(report.prose, record.facts):
        return report
    return report.model_copy(update={"prose": render_reply(report.prose, record.facts)})


def reconcile(report: LeadResponse, record: TurnRecord) -> list[Mismatch]:
    """Every way this reply, as the researcher reads it, disagrees with the turn
    it answers, in rule order."""
    shown = _as_read(report, record)
    found: list[Mismatch] = []
    for kind, rule in _RULES:
        sentence = rule(shown, record)
        if sentence is not None:
            found.append(Mismatch(kind=kind, sentence=sentence))
    return found


def unrendered_prose(replies: Sequence[str], record: TurnRecord) -> Mismatch | None:
    """A reply writes a fact outside a reference, or a reference names nothing
    the turn's facts hold."""
    faults = list(
        dict.fromkeys(f for text in replies for f in prose_faults(text, record.facts))
    )
    if not faults:
        return None
    return Mismatch(kind="unrendered_prose", sentence=unrendered_prose_message(faults))


def to_correct(
    ctx: RunContext[LeadDeps],
    report: LeadResponse,
    record: TurnRecord,
    replies: Sequence[str],
) -> list[Mismatch]:
    """The mismatches one answer is corrected for. Each of ``replies`` is read
    whole and refused every time it cannot render; every other mismatch is
    corrected once per message."""
    markers = ctx.deps.state.turn_markers
    prose = unrendered_prose(replies, record)
    found = [] if markers.contract_refused else reconcile(report, record)
    if found:
        markers.contract_refused = True
    return [*([] if prose is None else [prose]), *found]


def hold_the_turn_contract(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse an answer of a turn that does not match the turn's record.

    One correction carries every mismatch. Prose the product cannot render is
    refused on every answer; every other mismatch is asked once per turn.
    """
    if not isinstance(output, LeadResponse):
        return output
    mismatches = to_correct(ctx, output, turn_record(ctx), [output.prose])
    if not mismatches:
        return output
    raise ModelRetry(correction_for(mismatches))


def correction_for(mismatches: Sequence[Mismatch]) -> str:
    """The one correction that lists every mismatch under one heading."""
    return "\n\n".join([CONTRACT_HEADING, *(m.sentence for m in mismatches)])
