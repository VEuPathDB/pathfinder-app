"""Why the Lead's reply is refused when it does not match the turn it answers.

One sentence per rule of the turn contract, written for the model to act on.
"""

from __future__ import annotations

from collections.abc import Sequence

from strategist.domain.strategy.operational_spec import Criterion


def off_topic_essay_message(max_chars: int) -> str:
    """Why an out-of-scope reply that answers the request anyway is refused."""
    return (
        f"This turn asks for something Strategist does not do, and your reply "
        f"answers it. Write the redirect your instructions give instead: two "
        f"sentences, under {max_chars} characters, naming what Strategist does "
        f"and inviting the user to rephrase. No code block, no draft, no answer "
        f"to what was asked."
    )


def eda_criterion_not_built_message(waiting: Criterion) -> str:
    """Refuse an answer that leaves a criterion waiting for its analysis.

    Only the EDA tools write the analysis document, and only an export puts
    the criterion's step in the strategy.
    """
    dataset = waiting.needs_analysis_on
    return (
        f"The spec holds [{waiting.id}] {waiting.text!r}, which only the "
        f"analysis workflow builds, and no step exports it yet from dataset "
        f"{dataset}. Build it now: open_eda_analysis("
        f'dataset_id="{dataset}"), then set_eda_filters, then '
        f"preview_eda_subset, then create_eda_step("
        f'criterion_id="{waiting.id}"), which puts the step where the '
        f"structure places it. Never ask the user for an analysis "
        f"specification document, and never answer that the criterion cannot "
        f"be built or mapped: create_eda_step writes that document from the "
        f"analysis you filtered. A cut that neither the researcher's words nor "
        f"one of the study's own classes settles is a question: ask it with "
        f"consult_user."
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
                "turn, and a source is one a research read or read_gene_record "
                "returned this turn. "
                "Return the same digest with every sampled gene and source "
                "taken from what this turn read, or leave out what it did not."
            ),
        ]
    )
