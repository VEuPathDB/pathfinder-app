"""Lead arcs on the turn's control flow: a classification sent again, a record
read again, a count comparison that changes no step, and a comparison whose
UNION the structure refuses."""

from __future__ import annotations

from typing import Any

from assistant_core.models.scripted import (
    called_tool_parts,
    current_scope_id,
    current_turn,
    scripted_call,
    terminal_call,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import CLASSIFY, classify, lead_final
from pathfinder.ai.models.mock.frame_arcs import spec_frame
from pathfinder.ai.models.mock.reads import refusal_of
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import union_spec

# A turn that sends one classification this many times after the first.
REPEATED_CLASSIFICATIONS = 4
# The records a read-again turn reads, each twice.
READ_AGAIN_RECORDS = 3

_ANSWERED = (
    "The question is answered from the comparison beside this reply, and the "
    "strategy is as it was."
)
_READ = "The genes you named are listed beside this reply, each from its record."
_COMPARED = (
    "The comparison beside this reply counts both searches on the site, and the "
    "strategy keeps its steps and its count. Say which one to carry into the "
    "strategy and I will change it."
)


def _made(messages: list[ModelMessage], tool: str) -> int:
    return sum(p.tool_name == tool for p in called_tool_parts(current_turn(messages)))


def reclassified(messages: list[ModelMessage]) -> ToolCallPart:
    """The same classification sent again after the first, then the answer."""
    sent = _made(messages, CLASSIFY)
    if sent > REPEATED_CLASSIFICATIONS:
        return lead_final(_ANSWERED, "complete")
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "classification": "follow_up_question",
                "inferredGoal": f"[mock] the question, pass {sent + 1}",
            }
        },
    )


def read_again(messages: list[ModelMessage]) -> ToolCallPart:
    """Each of a few records read twice in turn, then the answer."""
    if not _made(messages, CLASSIFY):
        return classify("follow_up_question")
    genes = SiteValues.for_site(current_scope_id.get()).controls.positive_ids
    shown = list(genes[:READ_AGAIN_RECORDS])
    reads = _made(messages, "read_gene_record")
    if reads >= 2 * len(shown):
        return lead_final(_READ, "complete")
    return scripted_call("read_gene_record", {"gene_id": shown[reads % len(shown)]})


def _fields_variant(label: str, fields: list[str], organism: str) -> dict[str, Any]:
    return {
        "label": label,
        "search_name": "GenesByText",
        "parameters": {
            "text_expression": {"type": "string", "value": "kinase"},
            "text_fields": {"type": "multi-pick-vocabulary", "values": fields},
            "document_type": {"type": "string", "value": "gene"},
            "text_search_organism": {
                "type": "multi-pick-vocabulary",
                "values": [organism],
            },
        },
    }


def count_comparison(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """A question that compares two counts, answered by the comparison alone."""
    del messages
    organism = SiteValues.for_site(current_scope_id.get()).organism
    return [
        scripted_call(
            CLASSIFY,
            {
                "intent": {
                    "classification": "follow_up_question",
                    "inferredGoal": "[mock] compare the product search with notes",
                    "isDifferential": True,
                    "differentialSides": ["product field", "product and notes"],
                }
            },
        ),
        scripted_call(
            "compare_search_variants",
            {
                "variants": [
                    _fields_variant("product field", ["product"], organism),
                    _fields_variant(
                        "product and notes", ["product", "Notes"], organism
                    ),
                ]
            },
        ),
        lead_final(_COMPARED, "await_user"),
    ]


def union_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Bind two criteria under a UNION; a refused structure ends the pass on
    the refusal, with nothing bound."""
    refused = refusal_of(messages, "set_structure")
    if refused is not None:
        return terminal_call(
            {
                "summary": refused,
                "disposition": "needs_research",
                "openQuestions": [],
                "unstated": [],
            }
        )
    return spec_frame(union_spec)(messages)


def comparison_after_a_refused_union(
    messages: list[ModelMessage],
) -> list[ToolCallPart]:
    """An edit whose UNION the structure refuses, answered by the comparison."""
    return [
        classify("extend_strategy"),
        scripted_call("edit_strategy", {"reason": "[mock] compare the two counts"}),
        *count_comparison(messages)[1:],
    ]
