"""Why the Lead's reply is refused when it does not match the turn it answers.

One sentence per rule of the turn contract, written for the model to act on.
"""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion


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
            (
                "A sampled gene is one whose record read_gene_record returned this "
                "turn, and a source is one research_literature_search, "
                "research_web_search or read_gene_record returned this turn. "
                "Return the same digest with every sampled gene and source "
                "taken from what this turn read, or leave out what it did not."
            ),
        ]
    )
