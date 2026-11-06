from __future__ import annotations

import re
from typing import Any, Final

from assistant_core.models.scripted import (
    current_scope_id,
    next_unmade_call,
    scripted_call,
    scripted_text,
)
from pydantic_ai.messages import ModelMessage, TextPart, ToolCallPart

from pathfinder.ai.models.mock.arc_args import SIGNALP_VERSIONS
from pathfinder.ai.models.mock.message_words import message
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE

EXPLORE_ARC: Final = "explore"
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


def explore_readings(messages: list[ModelMessage]) -> ToolCallPart:
    organism = SiteValues.for_site(current_scope_id.get()).organism
    sequence = [
        scripted_call("propose_readings", _readings(organism)),
        *_kept_preference(),
        scripted_call("consult_user", _card()),
    ]
    return next_unmade_call(sequence, messages)


def no_reading(messages: list[ModelMessage]) -> TextPart:
    del messages
    return scripted_text(NO_READING)
