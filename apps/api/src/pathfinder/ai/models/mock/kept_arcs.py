"""The Lead arcs that act on what the researcher keeps, or answer from a read:
a gene set, a preference, the ledger, a gene record, a control set."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    current_scope_id,
    joined_user_text,
    scripted_call,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.conversation.gene_list_marker import parse_gene_list_marker
from pathfinder.ai.models.mock.arc_args import variant_args
from pathfinder.ai.models.mock.calls import CLASSIFY, classify, lead_final, narrated
from pathfinder.ai.models.mock.lead_flow import check_or_build
from pathfinder.ai.models.mock.message_words import (
    message,
    named_after,
    pasted_controls,
)
from pathfinder.ai.models.mock.reads import (
    gene_records,
    gene_set_id,
    instructions_of,
    text_return,
)
from pathfinder.ai.models.mock.site_values import SiteValues

SAVED_GENE_SET_NAME = "Mock gene set"
_SAVE_PROSE = "You can export it and publish it to your workspace."
_EXPORT_PROSE = "The file is ready; its download is shown beside this reply."
_NO_GENE_SET = "You have no saved gene set on this site to export."
_REMEMBER_PROSE = (
    "Stored for future conversations. I built nothing - say the word and I "
    "will turn it into a strategy."
)
_RECALL_PROSE = "This conversation already carries: "
_RECALL_NOTHING = "no ledger yet"
_RECALL_SHOWN = "the strategy shown beside this reply"
_NO_PREFERENCE = "I hold no stored preference of yours."
_VARIANT_PROSE = (
    "I ran both search variants and compared their results above. Tell me "
    "which direction you'd like to carry into the strategy."
)
_NEGATIVES_QUESTION = "Which genes should I use as negative controls?"
_CONTROLS_PROSE = (
    "I've saved your uploaded gene IDs as the positive controls of a control "
    f"set. {_NEGATIVES_QUESTION}"
)
PASTED_CONTROLS_NAME = "Controls from this message"
_PREFERENCE = re.compile(r"^- \[preference\] [^:]*: (?P<summary>.+)$", re.MULTILINE)


def _site() -> SiteValues:
    return SiteValues.for_site(current_scope_id.get())


def save_gene_set() -> list[ToolCallPart]:
    """Save the root step's genes under the name the message gives: the
    gene-set tool, never the memory note. The facts part shows the set's name
    and count."""
    name = named_after("named") or SAVED_GENE_SET_NAME
    return [
        classify("follow_up_question"),
        scripted_call("save_gene_set", {"name": name}),
        lead_final(f"Saved as the gene set {name}. {_SAVE_PROSE}", "await_user"),
    ]


def export(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Export the set the listing names first, on the id the listing gave."""
    head = [classify("follow_up_question"), scripted_call("list_gene_sets", {})]
    listed = text_return(messages, "list_gene_sets") is not None
    found = gene_set_id(messages)
    if listed and found is None:
        return [*head, lead_final(_NO_GENE_SET, "await_user")]
    return [
        *head,
        scripted_call(
            "export_gene_set", {"gene_set_id": found or "", "output_format": "csv"}
        ),
        lead_final(_EXPORT_PROSE, "await_user"),
    ]


def remember() -> list[ToolCallPart]:
    """Store the message as a preference, word for word, and build nothing."""
    stated = message()
    return [
        classify("memory_request"),
        scripted_call(
            "remember",
            {
                "kind": "preference",
                "name": "stated preference",
                "summary": stated,
                "content": {"statement": stated},
            },
        ),
        lead_final(narrated(f"{_REMEMBER_PROSE} Stored: {stated}"), "await_user"),
    ]


def recall_preference(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Answer with the preference the recalled memories pin, building nothing."""
    found = _PREFERENCE.search(instructions_of(messages))
    prose = _NO_PREFERENCE if found is None else found["summary"]
    return [classify("follow_up_question"), lead_final(prose, "await_user")]


def recap(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read one Ledger section and the live strategy, and answer with what the
    section says in words, dispatching no sub-agent. The facts part shows the
    steps and their counts."""
    section = text_return(messages, "read_ledger_section") or _RECALL_NOTHING
    kept = narrated(section).rstrip(".") or _RECALL_SHOWN
    return [
        scripted_call("read_ledger_section", {"section": "frame"}),
        scripted_call("get_live_strategy_state", {}),
        lead_final(f"{_RECALL_PROSE}{kept}.", "await_user"),
    ]


def variants() -> list[ToolCallPart]:
    return [
        classify("follow_up_question"),
        scripted_call("compare_search_variants", variant_args(_site().organism)),
        lead_final(_VARIANT_PROSE, "await_user"),
    ]


def attachment(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Save the gene ids an attached file carried as the positives of a control
    set, and ask for the negatives."""
    attached = parse_gene_list_marker(joined_user_text(messages))
    if attached is None:
        return [lead_final("No attached gene-ID list reached this turn.", "await_user")]
    return [
        scripted_call(
            CLASSIFY,
            {
                "intent": {
                    "classification": "new_strategy",
                    "inferredGoal": "[mock] save the attached positive controls",
                    "namedControls": {
                        "positiveIds": attached.gene_ids,
                        "negativeIds": [],
                    },
                },
            },
        ),
        scripted_call(
            "build_control_set",
            {
                "name": f"Controls from {attached.file_name}",
                "positive_ids": attached.gene_ids,
            },
        ),
        lead_final(_CONTROLS_PROSE, "await_user", questions=[_NEGATIVES_QUESTION]),
    ]


def controls_test(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Save the controls the message pastes as a control set, then check the
    strategy the thread holds, building one first when it holds none."""
    checked = check_or_build(messages)
    pasted = pasted_controls()
    if pasted is None:
        return checked
    positives, negatives = pasted
    saved = scripted_call(
        "build_control_set",
        {
            "name": PASTED_CONTROLS_NAME,
            "positive_ids": positives,
            "negative_ids": negatives,
        },
    )
    return [checked[0], saved, *checked[1:]]


def gene_question(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read one control gene's record and answer from it, building nothing.

    The facts part holds the record's link, so the reply names no gene id.
    """
    gene_id = _site().controls.positive_ids[0]
    records = gene_records(messages)
    record = records[-1] if records else None
    prose = (
        "The record did not answer."
        if record is None
        else narrated(
            f"The record names its product as {record.product or 'unnamed'}. "
            "The record's link is shown beside this reply."
        )
    )
    return [
        classify("follow_up_question"),
        scripted_call("read_gene_record", {"gene_id": gene_id}),
        lead_final(prose, "await_user"),
    ]
