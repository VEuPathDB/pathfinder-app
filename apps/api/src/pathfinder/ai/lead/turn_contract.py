"""The Lead's typed reply and the reconciliation that holds it against the
record of the turn it answers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, REPLY_NOTE
from pathfinder.ai.lead.contract_messages import (
    eda_criterion_not_built_message,
    note_facts_message,
    off_topic_essay_message,
    unclassified_turn_message,
    unsaved_controls_message,
    unverified_build_message,
)
from pathfinder.ai.lead.limit_messages import (
    unfollowed_reach_message,
    unmet_requirement_message,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_record import TurnRecord, turn_record
from pathfinder.ai.lead.verdict_claims import open_value_in_prose
from pathfinder.domain.clipped import list_clipped_to, text_clipped_to
from pathfinder.domain.reply_note import note_facts
from pathfinder.domain.strategy.questions import AskedQuestion

LeadTurnState = Literal["await_user", "complete"]

# An out-of-scope reply is a redirect, and a redirect is two sentences.
OFF_TOPIC_REPLY_MAX_CHARS = 400
_ASKED_LIMIT = 8
_CODE_FENCE = "```"

CONTRACT_HEADING = "This reply does not match what the turn did:"


class LeadResponse(CamelModel):
    """The Lead's final reply. ``prose`` is the note beside the facts the
    product renders; ``next_state`` says whether the turn waits on the user."""

    prose: Annotated[str, text_clipped_to(PROSE_MAX_CHARS)] = Field(
        description=(
            f"User-facing reply for this turn. Plain markdown. {REPLY_NOTE} "
            "Do NOT include sub-agent log noise - synthesize from the Ledger."
        ),
    )
    next_state: LeadTurnState = "await_user"
    unverified_reason: str = Field(
        default="",
        description=(
            "Only when this turn changed the strategy and verify_strategy cannot "
            "run right now: why, in one sentence the reply also states. Empty "
            "otherwise."
        ),
    )
    asked_questions: Annotated[list[AskedQuestion], list_clipped_to(_ASKED_LIMIT)] = (
        Field(
            default_factory=list,
            description=(
                "One entry per question this reply asks the user, carrying the "
                "value you recommend for it and the dimension it decides. A "
                "question you ask in prose and leave out of here is one the next "
                "turn has to ask again."
            ),
        )
    )


MismatchKind = Literal[
    "unverified_build",
    "unbuilt_eda_criterion",
    "open_value_in_prose",
    "unclassified_turn",
    "unsaved_controls",
    "off_topic_essay",
    "note_facts",
    "unfollowed_reach",
    "unmet_requirement",
    "unplanned_audit",
]


class Mismatch(CamelModel):
    """One way the reply and the record disagree, and the sentence that says so."""

    model_config = ConfigDict(frozen=True)

    kind: MismatchKind
    sentence: str


def _unverified_build(report: LeadResponse, record: TurnRecord) -> str | None:
    """A turn that built and reached no check answers for work nothing saw.

    The facts state the status, never the prose. A typed reply states in
    ``unverified_reason`` why a check that stopped or was refused could not
    finish.
    """
    if not record.build_unverified or record.ends_on_a_card:
        return None
    if report.unverified_reason.strip() and record.check_could_not_finish:
        return None
    return unverified_build_message(
        record.build_outcome,
        record.facts.root_count,
        could_not_finish=record.check_could_not_finish,
    )


def _unbuilt_eda_criterion(report: LeadResponse, record: TurnRecord) -> str | None:
    """Only the EDA tools build a criterion waiting for its analysis."""
    del report
    if not record.turn_builds or record.eda_criterion_pending is None:
        return None
    return eda_criterion_not_built_message(record.eda_criterion_pending)


def _open_value_in_prose(report: LeadResponse, record: TurnRecord) -> str | None:
    """A value the frame leaves open is asked on the question card."""
    del report
    return open_value_in_prose(record)


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


def _unfollowed_reach(report: LeadResponse, record: TurnRecord) -> str | None:
    reach = record.unfollowed_reach
    if reach is None or report.asked_questions or record.ends_on_a_card:
        return None
    return unfollowed_reach_message(
        reach, [t.path for t in record.facts.tallies if t.path is not None]
    )


def _unmet_requirement(report: LeadResponse, record: TurnRecord) -> str | None:
    unmet = record.unmet_requirements
    if not unmet or report.next_state != "complete":
        return None
    return unmet_requirement_message(unmet)


type _Rule = tuple[MismatchKind, Callable[[LeadResponse, TurnRecord], str | None]]

_RULES: tuple[_Rule, ...] = (
    ("unverified_build", _unverified_build),
    ("unbuilt_eda_criterion", _unbuilt_eda_criterion),
    ("open_value_in_prose", _open_value_in_prose),
    ("unclassified_turn", _unclassified_turn),
    ("unsaved_controls", _unsaved_controls),
    ("off_topic_essay", _off_topic_essay),
    ("unfollowed_reach", _unfollowed_reach),
    ("unmet_requirement", _unmet_requirement),
    ("unplanned_audit", lambda r, t: t.unplanned_audit(asked=bool(r.asked_questions))),
)


def reconcile(report: LeadResponse, record: TurnRecord) -> list[Mismatch]:
    """Every way this reply disagrees with the turn it answers, in rule order."""
    return [
        Mismatch(kind=kind, sentence=sentence)
        for kind, rule in _RULES
        if (sentence := rule(report, record)) is not None
    ]


def facts_in_the_note(replies: Sequence[str], record: TurnRecord) -> Mismatch | None:
    written = list(
        dict.fromkeys(t for text in replies for t in note_facts(text, record.facts))
    )
    if not written:
        return None
    return Mismatch(kind="note_facts", sentence=note_facts_message(written))


def to_correct(
    ctx: RunContext[LeadDeps],
    report: LeadResponse,
    record: TurnRecord,
    replies: Sequence[str],
) -> list[Mismatch]:
    """The mismatches one answer is corrected for. Each of ``replies`` is read
    whole for the facts it writes on a bound of its own; every other mismatch
    is corrected once per turn. An answer let through with a mismatch marks the
    turn's reply as unchecked."""
    markers = ctx.deps.state.turn_markers
    written = facts_in_the_note(replies, record)
    found = [
        m for m in reconcile(report, record) if m.kind not in markers.refused_rules
    ]
    note_asked = written is not None and may_refuse(ctx, markers.prose_refusals)
    rules_asked = bool(found) and may_refuse(ctx, markers.output_refusals)
    asked = [*([written] if written is not None and note_asked else []), *found]
    if note_asked or rules_asked:
        if note_asked:
            markers.prose_refusals += 1
        if rules_asked:
            markers.output_refusals += 1
            markers.refused_rules.extend(m.kind for m in found)
            markers.contract_refused = True
        return asked if rules_asked else asked[:1]
    if written is not None or reconcile(report, record):
        markers.unchecked_reply = True
    return []


def hold_the_turn_contract(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse an answer of a turn that does not match the turn's record.

    One correction carries every mismatch. A note that writes a link or a
    number is refused up to its own bound, then shown marked unchecked. Every
    other mismatch is asked once per turn.
    """
    if not isinstance(output, LeadResponse):
        return output
    mismatches = to_correct(ctx, output, turn_record(ctx), [output.prose])
    if mismatches:
        raise ModelRetry(correction_for(mismatches))
    return output


def correction_for(mismatches: Sequence[Mismatch]) -> str:
    """The one correction that lists every mismatch under one heading."""
    return "\n\n".join([CONTRACT_HEADING, *(m.sentence for m in mismatches)])
