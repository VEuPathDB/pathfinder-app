"""Why the Lead's reply is refused when it does not match the turn it answers.

One sentence per rule of the turn contract, written for the model to act on.
"""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.graph.tool_summary import count_noun

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.turn_records import CreatedControlSet, NamedStep
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.domain.evidence import RequirementCheck
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.orthology import OrganismChange
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.strategy.step_words import AddedSearch


def unrecorded_question_message() -> str:
    """Why a reply that asks the user something and records nothing is refused."""
    return (
        "Your reply asks the user a question and records none. The next turn "
        "reads ``asked_questions``, not your prose, so a question that is not "
        "there is asked again and a value you recommend is lost. Return the "
        "same reply with one ``asked_questions`` entry per question: the "
        "question, the value you recommend for it, and the dimension it "
        "decides."
    )


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


def misnamed_deletion_message(claimed: str, deleted: Sequence[NamedStep]) -> str:
    """Why a reply that names a step the turn did not delete is refused."""
    removed = ", ".join(step.described() for step in deleted)
    return (
        f"Your reply says it removed the {claimed} step, and that step is still "
        f"in the strategy. This turn deleted {removed}. Name the step that was "
        f"deleted, by its title."
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


def unverified_build_message(outcome: BuildOutcome | None) -> str:
    """Why a turn that built something is asked to verify before it answers.

    The check is asked for once. A second answer that still declines is the
    model's to give: only it knows whether a check is possible right now.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    root = outcome.root_count if outcome is not None else None
    count = "unknown" if root is None else str(root)
    return (
        f"This turn changed the strategy - {pushed} step(s) on VEuPathDB, root "
        f"count {count} - and nothing verified the result. Call verify_strategy, "
        f"or state in your reply why verification is not possible right now."
    )


def claimed_change_message(outcome: BuildOutcome | None) -> str:
    """Why a reply that reports a change this turn never made is refused.

    The turn's own record of what it wrote is the only evidence. It is asked
    once per turn.
    """
    pushed = len(outcome.pushed_step_ids) if outcome is not None else 0
    root = outcome.root_count if outcome is not None else None
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


def unreported_change_message() -> str:
    """Why a reply that leaves out the change this turn made is refused."""
    return (
        "This turn changed the strategy (a build, edit, delete, clear or "
        "export ran). Set strategy_changed to true and state what changed "
        "and the new counts."
    )


def _mislabelled_save_message(claimed: str, saves_it: str, instead: str) -> str:
    """Why a reply that reports an artifact this turn never saved is refused.

    A control set and a gene set are reached from different controls in the
    Evaluate panel, so the wrong noun sends the reader to the wrong place.
    """
    return (
        f"Your reply says this turn saved {claimed}, and this turn saved none: "
        f"{saves_it} is the only tool that saves one, and reading a result "
        f"saves nothing.{instead} A control set and a gene set are reached from "
        f"different controls in the Evaluate panel, so name what this turn "
        f"actually saved, or call {saves_it} and answer again."
    )


def control_set_not_written_message(saved: Sequence[CreatedGeneSet]) -> str:
    """Why a reply that reports a control set this turn never wrote is refused."""
    return _mislabelled_save_message(
        "a control set",
        "build_control_set",
        "".join(
            f" This turn saved the workbench gene set {created.name!r}, "
            f"{created.gene_count} genes."
            for created in saved[:1]
        ),
    )


def gene_set_not_saved_message(saved: Sequence[CreatedControlSet]) -> str:
    """Why a reply that reports a gene set this turn never saved is refused."""
    return _mislabelled_save_message(
        "a gene set",
        "save_gene_set",
        "".join(
            f" This turn saved the control set {created.name!r}."
            for created in saved[:1]
        ),
    )


def unretrieved_source_message(absent: Sequence[str]) -> str:
    """Why a reply that cites a reference this turn never read is refused."""
    named = ", ".join(absent)
    return (
        f"Your reply lists {named} under ``sources``, and no read of this turn "
        f"returned it: this is a reference this turn did not retrieve, so the "
        f"user cannot check it. Either drop it, or retrieve it first - "
        f"``read_gene_record`` for a fact about a gene, "
        f"``research_literature_search`` for a paper, ``research_web_search`` "
        f"for a page - and list what came back."
    )


_COPY_THE_CARD = (
    "Control counts and control gene ids are read from the control tests, the "
    "scored comparisons and the sweeps this turn ran, from the evidence card "
    "of the last check, and from the separation offer this reply's card "
    "carries or the conversation adopted. A count of sampled genes that fit is read from the "
    "sample the check judged. Copy them; never restate one from memory. When "
    "none of them holds a result, report no result."
)


def unbacked_evidence_message(found: Sequence[str]) -> str:
    """Why a reply that states a result no check of this turn holds is refused."""
    return " ".join(
        [
            *found,
            _COPY_THE_CARD,
            (
                "Return the same reply with every control count, control gene id "
                "and sampled-gene count taken from the evidence card, or leave out "
                "what the card does not hold."
            ),
        ]
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


def machine_words_message(found: Sequence[str]) -> str:
    """Why a reply about a failed turn that prints an internal name is refused."""
    named = ", ".join(found)
    return (
        f"This turn ends with work undone and your reply prints {named}. The "
        f"user holds no tool name, no step id and no error code, so none of "
        f"them says what went wrong. {THE_PLAIN_SENTENCE} Then ask the one "
        f"question that unblocks it, or stop."
    )


def unnamed_search_message(
    missing: Sequence[AddedSearch], unreasoned: Sequence[AddedSearch] = ()
) -> str:
    """Why a reply that does not name a search this turn added, or names it
    without the reason it was chosen, is refused.

    The step runs the search, not the words it was chosen for, so a reply in
    the request's words alone can say the strategy holds a filter it lacks.
    """
    sentences: list[str] = []
    if missing:
        listed = "; ".join(
            f"{added.search_display_name} (for: {added.criterion_text})"
            for added in missing
        )
        sentences.append(
            f"This turn added steps your reply does not name by the search they "
            f"run: {listed}. Name each search as written here, and say what it "
            f"finds; when it is not what the request asked for, say so."
        )
    reasoned = [(a, a.rationale) for a in unreasoned if a.rationale is not None]
    if reasoned:
        listed = "; ".join(
            f"{added.search_display_name} (for: {added.criterion_text}) - "
            f"{rationale.line()}"
            for added, rationale in reasoned
        )
        sentences.append(
            f"These are named without the reason they were chosen: {listed}. "
            f"Give each reason beside its name, in the same paragraph or list "
            f"item, as written here or in your words, keeping the term."
        )
    return " ".join(sentences)


def unnamed_record_organism_message(change: OrganismChange) -> str:
    """Why a reply about records another organism holds, not naming it, is refused.

    A count read as the seed's organism is a count of genes the researcher did
    not search.
    """
    records = ", ".join(change.records)
    return (
        f"The strategy's records are genes of {records}, and the seed searched "
        f"{', '.join(change.seed)}. Your reply does not say whose genes these "
        f"are. Name {records} beside the count, in full or with the genus "
        f"abbreviated."
    )


def unreported_requirement_message(rows: Sequence[RequirementCheck]) -> str:
    """Why a reply silent about a requirement its check found unmet is refused.

    A reply that names only what the strategy meets reads as a strategy that
    meets everything the researcher asked.
    """
    listed = "; ".join(f"'{row.text}' ({row.status}: {row.note})" for row in rows)
    return (
        f"The check reports requirements the strategy does not meet: {listed}. "
        f"Your reply does not name them. Name each as written here, and say what "
        f"the strategy returns without it."
    )


def unstated_qualifier_message(words: Sequence[str]) -> str:
    """Why a reply that is silent about a requirement no search could state is refused.

    The strategy was built without it, so a reply that stays silent reads as
    a strategy that honours it.
    """
    listed = ", ".join(f"'{word}'" for word in words)
    return (
        f"The request states {listed}, and no search this pass read has a "
        f"parameter that states it, so the strategy does not. Say so in the "
        f"reply, naming each word, and what the strategy returns without it."
    )


def counted_in_the_wrong_unit_message(
    record_type: str, noun: str, counts: Sequence[int]
) -> str:
    """Why a reply that names a step count in the record type's own noun is refused.

    The site counts a transcript strategy in genes, so "145 transcripts" reads
    as more transcripts than genes and misstates the count.
    """
    written = " and ".join(f"{count:,} {record_type}s" for count in counts)
    wanted = " and ".join(f"{count:,} {noun}s" for count in counts)
    return (
        f"The strategy holds {record_type} records, and the site counts them in "
        f"{noun}s: your reply writes {written}. Write {wanted}."
    )
