"""The Lead arcs that act on what the researcher keeps, or answer from a read:
a gene set, a preference, the ledger, a gene record, a control set."""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    current_scope_id,
    deferred_tool_resolved,
    joined_user_text,
    scripted_call,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc_args import (
    attached_gene_list,
    consult_args,
    variant_args,
)
from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.lead_flow import build_journey
from pathfinder.ai.models.mock.message_words import message, named_after
from pathfinder.ai.models.mock.reads import (
    empty_steps_sentence,
    exported_link,
    gene_records,
    gene_set_id,
    instructions_of,
    live_count_sentence,
    saved_gene_count,
    text_return,
)
from pathfinder.ai.models.mock.site_values import SiteValues

SAVED_GENE_SET_NAME = "Mock gene set"
_SAVE_PROSE = (
    "You can export it, publish it to your workspace, and test controls against it."
)
_EXPORT_PROSE = "The file is ready. Download it here: "
_NO_GENE_SET = "You have no saved gene set on this site to export."
_REMEMBER_PROSE = (
    "Stored for future conversations. I built nothing - say the word and I "
    "will turn it into a strategy."
)
_RECALL_PROSE = "This conversation already carries: "
_RECALL_NOTHING = "no ledger yet"
_NO_PREFERENCE = "I hold no stored preference of yours."
_VARIANT_PROSE = (
    "I ran both search variants and compared their results above. Tell me "
    "which direction you'd like to carry into the strategy."
)
_CONTROLS_PROSE = (
    "I've saved your uploaded gene IDs as a control set. We can now score "
    "search variants against them whenever you're ready."
)
_PREFERENCE = re.compile(r"^- \[preference\] [^:]*: (?P<summary>.+)$", re.MULTILINE)


def _site() -> SiteValues:
    return SiteValues.for_site(current_scope_id.get())


def save_gene_set(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Save the root step's genes under the name the message gives, and state
    how many the set holds: the gene-set tool, never the memory note."""
    name = named_after("named") or SAVED_GENE_SET_NAME
    count = saved_gene_count(messages)
    held = "" if count is None else f" with {count:,} genes"
    return [
        classify("follow_up_question"),
        scripted_call("save_gene_set", {"name": name}),
        lead_final(f"Saved as the gene set {name}{held}. {_SAVE_PROSE}", "await_user"),
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
        lead_final(f"{_EXPORT_PROSE}{exported_link(messages)}", "await_user"),
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
        lead_final(f"{_REMEMBER_PROSE} Stored: {stated}", "await_user"),
    ]


def recall_preference(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Answer with the preference the recalled memories pin, building nothing."""
    found = _PREFERENCE.search(instructions_of(messages))
    prose = _NO_PREFERENCE if found is None else found["summary"]
    return [classify("follow_up_question"), lead_final(prose, "await_user")]


def recap(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read one Ledger section and the live counts, and answer with both,
    naming each empty step, dispatching no sub-agent."""
    section = text_return(messages, "read_ledger_section") or _RECALL_NOTHING
    counts = " ".join(
        s for s in (live_count_sentence(messages), empty_steps_sentence(messages)) if s
    )
    return [
        scripted_call("read_ledger_section", {"section": "frame"}),
        scripted_call("get_live_strategy_state", {}),
        lead_final(f"{_RECALL_PROSE}{section}\n\n{counts}", "await_user"),
    ]


def variants() -> list[ToolCallPart]:
    return [
        classify("follow_up_question"),
        scripted_call("compare_search_variants", variant_args(_site().organism)),
        lead_final(_VARIANT_PROSE, "await_user"),
    ]


def attachment(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Save the gene ids an attached file carried as a control set."""
    attached = attached_gene_list(joined_user_text(messages))
    if attached is None:
        return [lead_final("No attached gene-ID list reached this turn.", "await_user")]
    return [
        classify("new_strategy"),
        scripted_call(
            "build_control_set",
            {"name": attached.control_set_name, "positive_ids": attached.gene_ids},
        ),
        lead_final(_CONTROLS_PROSE, "await_user"),
    ]


def gene_question(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read one control gene's record and answer from it, building nothing."""
    gene_id = _site().controls.positive_ids[0]
    records = gene_records(messages)
    record = records[-1] if records else None
    prose = (
        "The record did not answer."
        if record is None
        else f"{record.gene_id} encodes {record.product or 'an unnamed product'}."
    )
    sources = (
        [
            {
                "kind": "record",
                "label": f"{record.gene_id} on {current_scope_id.get()}",
                "url": record.record_url,
            }
        ]
        if record is not None and record.record_url
        else []
    )
    return [
        classify("follow_up_question"),
        scripted_call("read_gene_record", {"gene_id": gene_id}),
        lead_final(prose, "await_user", sources=sources),
    ]


def consult(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Ask the design questions; the answered card resumes the build."""
    if deferred_tool_resolved(messages, "consult_user"):
        return build_journey(messages)
    return [classify("new_strategy"), scripted_call("consult_user", consult_args())]
