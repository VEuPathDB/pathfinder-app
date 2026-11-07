from __future__ import annotations

import re
from typing import Any, Final

from assistant_core.models.scripted import (
    called_tool_parts,
    current_scope_id,
    current_turn,
    next_unmade_call,
    scripted_call,
    scripted_text,
)
from pydantic_ai.messages import ModelMessage, TextPart, ToolCallPart

from pathfinder.ai.models.mock.arc_args import SIGNALP_VERSIONS
from pathfinder.ai.models.mock.message_words import message
from pathfinder.ai.models.mock.prose_arcs import OFF_TOPIC_PROSE
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE

EXPLORE_ARC: Final = "explore"
ONE_READING_ARC: Final = "explore-one-reading"
FIRST_LABEL = "Genes with a predicted signal peptide"
SECOND_LABEL = "Every protein-coding gene"
READINGS_QUESTION = "Which reading should the strategy build?"
READINGS_REPLY = (
    "[mock] Two readings the site can build answer this question. The first "
    "reads the site's signal peptide search and the second its gene type "
    "search, and each option shows the genes the site counts for it. My "
    "hypothesis is that the first reading answers the question more closely, "
    "since the second holds every protein-coding gene."
)
NO_READING = (
    "[mock] The site holds no search that states this as asked, so I propose "
    "no reading. My hypothesis is that the literature names it under another "
    "term; switch to Build when you want a strategy."
)
ONE_READING = (
    "[mock] The site's signal peptide search states this as asked, and the "
    "facts beside this reply show the genes it counts. Switch to Build, or "
    'say "build it" in Auto, to have it built.'
)
_PREFERENCE = re.compile(r"\bprefer", re.IGNORECASE)


def _multi(*values: str) -> dict[str, Any]:
    return {"type": "multi-pick-vocabulary", "values": list(values)}


def _single(value: str) -> dict[str, Any]:
    return {"type": "single-pick-vocabulary", "value": value}


def _readings(organism: str) -> dict[str, Any]:
    return {
        "readings": [
            {
                "label": FIRST_LABEL,
                "search_name": SIGNAL_PEPTIDE,
                "parameters": {
                    "organism": _multi(organism),
                    "signalp_version": _single(SIGNALP_VERSIONS[0]),
                },
            },
            {
                "label": SECOND_LABEL,
                "search_name": GENE_TYPE,
                "parameters": {
                    "organism": _multi(organism),
                    "geneType": _multi("protein coding"),
                    "includePseudogenes": _single("No"),
                },
            },
        ]
    }


def _card() -> dict[str, Any]:
    return {
        "reply": READINGS_REPLY,
        "questions": [
            {
                "id": "reading",
                "prompt": READINGS_QUESTION,
                "options": [{"label": FIRST_LABEL}, {"label": SECOND_LABEL}],
                "allowNotes": False,
            }
        ],
    }


def _kept_preference() -> list[ToolCallPart]:
    stated = message()
    if _PREFERENCE.search(stated) is None:
        return []
    return [
        scripted_call(
            "remember",
            {
                "kind": "preference",
                "name": "stated preference",
                "summary": stated,
                "content": {"statement": stated},
            },
        )
    ]


def one_reading(messages: list[ModelMessage]) -> ToolCallPart | TextPart:
    counted = called_tool_parts(current_turn(messages))
    if any(call.tool_name == "propose_readings" for call in counted):
        return scripted_text(ONE_READING)
    organism = SiteValues.for_site(current_scope_id.get()).organism
    [first, _] = _readings(organism)["readings"]
    return scripted_call("propose_readings", {"readings": [first]})


def explore_readings(messages: list[ModelMessage]) -> ToolCallPart:
    organism = SiteValues.for_site(current_scope_id.get()).organism
    sequence = [
        scripted_call("propose_readings", _readings(organism)),
        *_kept_preference(),
        scripted_call("consult_user", _card()),
    ]
    return next_unmade_call(sequence, messages)


def off_topic_reply(messages: list[ModelMessage]) -> TextPart:
    del messages
    return scripted_text(OFF_TOPIC_PROSE)


def no_reading(messages: list[ModelMessage]) -> TextPart:
    del messages
    return scripted_text(NO_READING)
