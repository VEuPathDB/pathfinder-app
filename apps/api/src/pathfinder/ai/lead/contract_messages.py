"""Why the Lead's reply is refused when it does not match the turn it answers.

One sentence per rule of the turn contract, written for the model to act on.
"""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.tool_summary import count_noun

from pathfinder.ai.lead.card_reply import REPLY_REFERENCES
from pathfinder.ai.lead.list_fault_messages import list_sentence
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.lead.reference_fault_messages import reference_sentence
from pathfinder.domain.reply_references import ProseFault
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.domain.turn_facts import TurnFacts


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


def unverified_build_message(
    outcome: BuildOutcome | None, root: int | None, *, could_not_finish: bool
) -> str:
    """Why a turn that built something is asked to verify before it answers.

    ``root`` is the count the facts show for the strategy. The check is asked
    for once. A reason stands only after a check of this turn stopped or was
    refused, so the reply cannot decline a check it never tried.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    count = "unknown" if root is None else str(root)
    move = (
        "Call verify_strategy, or set `unverifiedReason` to why it cannot run "
        "and state it in your reply."
        if could_not_finish
        else "Call verify_strategy. `unverifiedReason` is accepted only after a "
        "check of this turn stopped or was refused."
    )
    return (
        f"This turn changed the strategy - {pushed} step(s) on VEuPathDB, root "
        f"count {count} - and nothing verified the result. {move}"
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


def unbacked_digest_message(found: Sequence[str]) -> str:
    """Why a digest that states what no read of this turn holds is refused."""
    return " ".join(
        [
            *found,
            _COPY_THE_CARD,
            (
                "A sampled gene is one whose record read_gene_record returned this "
                "turn, and a source is one research_literature_search, "
                "research_web_search or read_gene_record returned this turn. "
                "Return the same digest with every control count, "
                "control gene id, sampled gene and source taken from what this "
                "turn read, or leave out what it did not."
            ),
        ]
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


_SAID_IN_WORDS = {
    "sentence_in_place": "a stored sentence",
    "boolean_in_place": "a yes or no",
}


def _kind_sentence(fault: ProseFault) -> str | None:
    if fault.kind in _SAID_IN_WORDS:
        return (
            f"``{fault.token}`` names {_SAID_IN_WORDS[fault.kind]}, which never "
            "stands in the reply: say it in your words and write "
            f"``{fault.references[0]}`` after them."
        )
    if fault.kind == "cited_number":
        return (
            f"``{fault.token}`` names a number, which the reply writes in place: "
            f"write ``{fault.references[0]}``."
        )
    return None


def _placement_sentence(fault: ProseFault) -> str | None:
    """The rewrite for a misplaced reference or a record's product text."""
    if fault.kind == "noun_after_count":
        reference = fault.references[0]
        return (
            f"``{fault.token}``: ``{reference}`` renders the count with its noun, "
            "so write no noun after it: 'returns [count:step_a], the overall "
            "result', not 'returns [count:step_a] genes'."
        )
    if fault.kind == "standalone_count":
        return (
            f"``{fault.token}`` is that variant's size on its own, larger than the "
            "strategy's result with it in place, so it is no share of the result: "
            f"write ``{fault.references[0]}``, its count in the strategy."
        )
    if fault.kind == "product_text":
        return (
            f"``{fault.token}``: the product of {fault.record_id} renders from "
            f"``[record:{fault.record_id}]``; write the reference alone."
        )
    return None


def _fault_sentence(fault: ProseFault) -> str:
    if fault.kind == "unheld_reference" and fault.references:
        written = " or ".join(f"``{r}``" for r in fault.references)
        return (
            f"``{fault.token}`` names a group of values, not one value: write "
            f"{written} in place of the value it states, or take it out."
        )
    if fault.kind == "unheld_reference":
        return f"``{fault.token}`` names nothing the facts hold."
    if fault.kind == "malformed_reference":
        return (
            f"``{fault.token}`` is no reference the product reads: write one of "
            "the references above, or take the brackets out."
        )
    placed = (
        _kind_sentence(fault)
        or list_sentence(fault)
        or reference_sentence(fault)
        or _placement_sentence(fault)
    )
    if placed is not None:
        return placed
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


def failed_check_message(reason: str, unanswered: Sequence[str]) -> str:
    """Why a reply over a failed check that states nothing of it is refused."""
    stated = (
        f"name each requirement it found unanswered, {_named(unanswered)}"
        if unanswered
        else "quote its reason"
    )
    return (
        f"The last check of this strategy failed: {reason} Nothing has changed "
        f"since, so the reply states that verdict: {stated}. Or ask the "
        "researcher how to go on, recorded in ``asked_questions`` or on a card."
    )


def _named(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def unplaced_breakdown_message(references: Sequence[str]) -> str:
    return (
        "The reply places the group count of a computed comparison and not how "
        "those groups divide. A group that one set alone holds is absent from the "
        "other set, not larger in it, and the residual groups and a species that "
        "leads a set change what the count means. Place one reference of each item "
        f"with the words that say what it counts: {'; '.join(references)}."
    )
