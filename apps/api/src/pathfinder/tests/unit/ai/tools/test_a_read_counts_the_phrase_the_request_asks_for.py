"""A read-only count or membership check refuses a text term of several words
sent unquoted when the message asks for the exact phrase, before any report
runs, since the site reads an unquoted term as any of its words."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.tools.standalone.search_reads import count_search, genes_in_search
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.tests._support.run_context import lead_run_context

_ASKS = (
    "How many genes actually have the exact phrase 'cysteine-rich protein' in "
    "their product description? Just tell me, don't change the strategy yet."
)
_REFUSAL = (
    "text_expression on GenesByText: the request asks for the phrase, so the "
    'term is quoted: "cysteine-rich protein"; an unquoted term matches any of '
    "its words."
)


def _phrase_search(text: str) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "exact phrase in product description",
            "searchName": "GenesByText",
            "parameters": {
                "text_search_organism": {
                    "type": "multi-pick-vocabulary",
                    "values": ["Giardia muris strain Roberts-Thomson"],
                },
                "text_expression": {"type": "string", "value": text},
                "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
            },
        }
    )


async def test_a_count_of_an_unquoted_phrase_the_message_asks_for_is_refused() -> None:
    ctx = lead_run_context(site_id="giardiadb", user_prompt=_ASKS)

    with pytest.raises(ModelRetry) as refused:
        await count_search(ctx, _phrase_search("cysteine-rich protein"))

    assert refused.value.message == _REFUSAL


async def test_a_membership_check_of_an_unquoted_phrase_is_refused() -> None:
    ctx = lead_run_context(site_id="giardiadb", user_prompt=_ASKS)

    with pytest.raises(ModelRetry) as refused:
        await genes_in_search(
            ctx, _phrase_search("cysteine-rich protein"), gene_ids=["GMRT_10001"]
        )

    assert refused.value.message == _REFUSAL
