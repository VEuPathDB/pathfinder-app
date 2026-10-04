"""Why the Lead's reply is refused when it does not match the turn it answers.

One sentence per rule of the turn contract, written for the model to act on.
"""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.tool_summary import count_noun

from pathfinder.ai.lead.card_reply import REPLY_REFERENCES
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.evidence import RequirementCheck
from pathfinder.domain.reply_references import ProseFault
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.turn_facts import TurnFacts


def unrecorded_offer_message() -> str:
    """Why a reply that ends on a question and records nothing is refused."""
    return (
        "Your reply ends with a question and records nothing, so a yes on the "
        "next turn accepts nothing the conversation holds. When it offers further "
        "work, put the offer on a proposal card: call ``propose_changes`` with "
        "the reply as its ``reply``, the question in one "
        "sentence and each concrete change a yes makes. When it asks the user "
        "for a value, record the question in ``asked_questions`` with the value "
        "you recommend. Otherwise end the reply without a question."
    )


def off_topic_essay_message(max_chars: int) -> str:
    """Why an out-of-scope reply that answers the request anyway is refused."""
    return (
        f"This turn asks for something PathFinder does not do, and your reply "
        f"answers it. Write the redirect instead: two sentences, under "
        f"{max_chars} characters, naming what PathFinder does - strategies on "
        f"the VEuPathDB sites, EDA, exports - and inviting the "
        f"user to rephrase. No code block, no draft, no answer to what was "
        f"asked."
    )


def blamed_the_site_message(blame: str, stop: PhaseStop | None) -> str:
    """Why a reply that asks the user to wait for VEuPathDB is refused.

    The turn's own stop is the cause, so the refusal hands the model that
    sentence to write instead of an external one.
    """
    cause = (
        f"what stopped this turn is that {stop.render()}"
        if stop is not None
        else "no pass of this turn reported a stop"
    )
    return (
        f"Your reply attributes this turn's outcome to VEuPathDB ({blame}), and "
        f"no VEuPathDB call of this turn failed. Rewrite it: {cause}. State "
        f"that, state what happens next, and never ask the user to retry "
        f"because the site is busy."
    )


def unverified_build_message(outcome: BuildOutcome | None, root: int | None) -> str:
    """Why a turn that built something is asked to verify before it answers.

    ``root`` is the count the facts show for the strategy. The check is asked
    for once: only the model knows whether a check is possible right now.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    count = "unknown" if root is None else str(root)
    return (
        f"This turn changed the strategy - {pushed} step(s) on VEuPathDB, root "
        f"count {count} - and nothing verified the result. Call verify_strategy, "
        f"or state in your reply why verification is not possible right now."
    )


def claimed_change_message(outcome: BuildOutcome | None, root: int | None) -> str:
    """Why a reply that reports a change this turn never made is refused.

    The turn's own record of what it wrote is the only evidence, and ``root``
    is the count the facts show. It is asked once per turn.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    count = "unknown" if root is None else str(root)
    return (
        f"This reply says the strategy changed, but this turn ran no build, "
        f"edit, delete, clear or export: the strategy is exactly as the turn "
        f"found it - {pushed} step(s), root count {count}. Rewrite the reply "
        f"to describe the strategy as it is and what you would change, or "
        f"make the change with the tools and answer again."
    )


def claimed_frame_message(diff: SpecDiff) -> str:
    """Why a reply that reports a criterion this turn never framed is refused.

    The plan is what the next turn builds, so a criterion only the prose holds
    leaves the user answering questions about nothing.
    """
    return (
        f"This reply says the turn framed a criterion or added one to the plan, "
        f"and the plan is as the turn found it ({diff.render()}): nothing was "
        f"added and nothing changed. A question about a criterion the plan does "
        f"not hold is answered into nothing. Dispatch the pass that records it "
        f"- edit_strategy over a strategy, frame_problem without one - or "
        f"rewrite the reply to state what the plan holds and what you would "
        f"add. When that pass was refused or did not run, {THE_PLAIN_SENTENCE}"
    )


def eda_criterion_not_built_message(waiting: Criterion) -> str:
    """Refuse an answer that leaves a criterion waiting for its analysis.

    Only the EDA tools write the analysis document, so a turn that opened no
    analysis on the criterion's dataset has not tried to build it.
    """
    dataset = waiting.needs_analysis_on
    return (
        f"The spec holds [{waiting.id}] {waiting.text!r}, which only the "
        f"analysis workflow builds, and this turn opened no EDA analysis on "
        f"dataset {dataset}. Build it now: open_eda_analysis("
        f'dataset_id="{dataset}"), then set_eda_filters, then '
        f"preview_eda_subset, then create_eda_step("
        f'criterion_id="{waiting.id}"), which puts the step where the '
        f"structure places it. Never ask the user for an analysis "
        f"specification, and never answer that the criterion cannot be built "
        f"or mapped: create_eda_step writes that document from the analysis "
        f"you filtered."
    )


def unreported_change_message(outcome: BuildOutcome | None, facts: TurnFacts) -> str:
    """Why a reply that leaves out the change this turn made is refused.

    The steps this turn pushed are named, so the reply cannot describe them as
    a strategy an earlier turn left.
    """
    pushed = set(outcome.pushed_step_ids) if outcome is not None else set()
    built = [step.display_name for step in facts.steps if step.step_id in pushed]
    what = f": it built {', '.join(built)}" if built else ""
    count = (
        "an unknown count"
        if facts.root_count is None
        else count_noun(facts.root_count, facts.record_noun)
    )
    return (
        f"This turn changed the strategy (a build, edit, delete, clear or "
        f"export ran){what}. The root holds {count}. Set strategy_changed to "
        f"true and say what this turn built or changed, never that nothing "
        f"changed; the counts are shown beside the reply."
    )


def unclassified_turn_message(refusal: str) -> str:
    """Why a reply on a turn that holds no accepted classification is refused."""
    return (
        "This turn's message holds no accepted classification: "
        f"classify_user_intent refused it with this sentence. {refusal} Call "
        "classify_user_intent again with what the sentence names, or ask the "
        "researcher the question it states through consult_user."
    )


def unsaved_controls_message(positives: int, negatives: int) -> str:
    """Why a reply on a turn whose message names controls it never saved is refused."""
    return (
        f"The message names {positives} positive and {negatives} negative "
        "controls, and this turn saved no control set. Save them with "
        "build_control_set; with positives only, save them and ask for the "
        "negatives."
    )


_COPY_THE_CARD = (
    "Control counts and control gene ids are read from the control tests, the "
    "scored comparisons and the sweeps this turn ran, from the evidence card "
    "of the last check, and from the separation offer this reply's card "
    "carries or the conversation adopted. A count of sampled genes that fit is read from the "
    "sample the check judged. Copy them; never restate one from memory. When "
    "none of them holds a result, report no result."
)


def unread_gene_sentence(gene_id: str) -> str:
    """Why a sampled gene whose record the turn did not read cannot stand."""
    return (
        f"The review lists sampled gene `{gene_id}`, and no read_gene_record "
        f"call of this turn read its record."
    )


def unretrieved_review_source_sentence(reference: str) -> str:
    """Why a source no read of this turn returned cannot stand on the card."""
    return f"The review cites {reference}, and no read of this turn returned it."


def misnumbered_requirement_sentence(row: RequirementCheck, messages: int) -> str:
    """Why a requirement row that names a message the request lacks is refused."""
    return (
        f"The requirement '{row.text}' names message {row.turn}, and the request "
        f"has {count_noun(messages, 'message')}."
    )


def misnamed_answer_sentence(
    row: RequirementCheck, answer: str, held: Sequence[str]
) -> str:
    """Why a requirement row answered by an id the strategy lacks is refused."""
    return (
        f"The requirement '{row.text}' is answered by {answer}, which names no "
        f"step of the strategy; it holds {', '.join(held) or 'no step'}."
    )


def unbacked_digest_message(found: Sequence[str]) -> str:
    """Why a digest that states what no read of this turn holds is refused."""
    return " ".join(
        [
            *found,
            _COPY_THE_CARD,
            (
                "A sampled gene is one whose record read_gene_record returned this "
                "turn, and a source is one research_literature_search, "
                "research_web_search or read_gene_record returned this turn. A "
                "requirement names its message by the number the request block "
                "gives it. Return the same digest with every control count, "
                "control gene id, sampled gene and source taken from what this "
                "turn read, or leave out what it did not."
            ),
        ]
    )


def _what_did_not_run(refused: Sequence[str], stop: PhaseStop | None) -> str:
    """The dispatch that was refused, or the stop that ended the last pass."""
    if refused:
        return f"{' and '.join(refused)} refused this turn's call"
    return stop.render() if stop is not None else "no pass of this turn finished"


THE_PLAIN_SENTENCE = (
    "Tell the user in one plain sentence what did not work and what was not "
    'done ("I could not add the mass-spec filter, so the strategy is '
    'unchanged"), with no tool name, no step id and no error text.'
)


def unfinished_work_message(refused: Sequence[str], stop: PhaseStop | None) -> str:
    """Why a reply that ends a turn with the work undone and asks nothing is refused."""
    return (
        f"This turn ends with the work undone "
        f"({_what_did_not_run(refused, stop)}), and your reply records no "
        f"question, so nothing carries the work on and the user is given no way "
        f"to unblock it. Rewrite it: {THE_PLAIN_SENTENCE} Then ask the choice "
        f"that unblocks that pass and record it in ``asked_questions`` with the "
        f"value you recommend, or stop there. Never name a pass as the next "
        f"thing you will do - this reply ends the turn."
    )


def unstated_stop_message(stop: PhaseStop) -> str:
    """Why a reply that does not say the turn's check stopped is refused."""
    return (
        f"The check of this turn did not finish: {stop.render()}. It recorded no "
        f"verdict, so the strategy is not verified. Say that the verification "
        f"stopped before it finished, with no tool name, and ask whether to run "
        f"it again."
    )


def unnamed_record_organism_message(change: OrganismChange) -> str:
    """Why a reply about records another organism holds, not naming it, is refused.

    A count read as the seed's organism is a count of genes the researcher did
    not search.
    """
    records = ", ".join(change.records)
    return (
        f"The strategy's records are genes of {records}, and the seed searched "
        f"{', '.join(change.seed)}. Your reply does not say whose genes these "
        f"are. Name {records} in the reply, in full or with the genus "
        f"abbreviated."
    )


_WRITE_REFERENCES = (
    f"Your reply writes facts the product renders. {REPLY_REFERENCES} Keep "
    "every other part of the reply as it is."
)


def _placement_sentence(fault: ProseFault) -> str | None:
    """The rewrite for a misplaced reference or a record's product text."""
    if fault.kind == "number_word":
        return (
            f"``{fault.token}``: ``{fault.references[0]}`` stands in place of the "
            "number, so the clause writes no number word: write 'at least "
            "[value:step_x.min_tm] transmembrane domains', not 'at least one "
            "transmembrane domain [value:step_x.min_tm]'."
        )
    if fault.kind == "noun_after_count":
        reference = fault.references[0]
        return (
            f"``{fault.token}``: ``{reference}`` renders the count with its noun, "
            "so write no noun after it: 'returns [count:step_a], the overall "
            "result', not 'returns [count:step_a] genes'."
        )
    if fault.kind == "product_text":
        return (
            f"``{fault.token}``: the product of {fault.record_id} renders from "
            f"``[record:{fault.record_id}]``; write the reference alone."
        )
    return None


def _fault_sentence(fault: ProseFault) -> str:
    if fault.kind == "unheld_reference":
        return f"``{fault.token}`` names nothing the facts hold."
    if fault.kind == "malformed_reference":
        return (
            f"``{fault.token}`` is no reference the product reads: write one of "
            "the references above, or take the brackets out."
        )
    placed = _placement_sentence(fault)
    if placed is not None:
        return placed
    if fault.kind == "source_word" and fault.references:
        written = " or ".join(f"``{r}``" for r in fault.references)
        return (
            f"``{fault.token}``: put {written} in place of the word, which renders "
            "who set the value, or take the word out."
        )
    if fault.references:
        written = " or ".join(f"``{r}``" for r in fault.references)
        return f"``{fault.token}``: write {written}, which renders it."
    return f"``{fault.token}``: no fact holds it, so take it out."


def unrendered_prose_message(faults: Sequence[ProseFault]) -> str:
    """Why a reply that writes a fact itself, or names one the facts lack, is
    refused, with the reference that renders each fact."""
    return "\n".join(
        [_WRITE_REFERENCES, *(f"- {_fault_sentence(fault)}" for fault in faults)]
    )


def failed_check_message(reason: str) -> str:
    """Why a reply over a failed check that states nothing of it is refused."""
    return (
        f"The last check of this strategy failed: {reason} Nothing has changed "
        "since, so the reply states that verdict: name each requirement the "
        "check found unanswered, or quote its reason. Or ask the researcher how "
        "to go on, recorded in ``asked_questions`` or on a card."
    )


def unmade_change_message(withdrawn: Sequence[str], stated: Sequence[str]) -> str:
    """Why an edit turn that made no change, raised no card and stated no reason is refused."""
    if withdrawn:
        values, ask, act, how = withdrawn, "to remove", "remove", "delete_step"
        done = "removed"
    else:
        values, ask, act, how = stated, "for", "make", "edit_strategy"
        done = "made"
    named = ", ".join(f"'{value}'" for value in values)
    them = "it" if len(values) == 1 else "them"
    return (
        f"The message asks {ask} {named} and this turn made no change and raised "
        f"no card: {act} {them} through {how}, or say in the reply why {them} "
        f"cannot be {done}."
    )
