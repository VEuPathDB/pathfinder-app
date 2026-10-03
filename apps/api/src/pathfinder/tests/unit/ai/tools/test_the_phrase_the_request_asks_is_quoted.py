"""A text term the request asks for as a phrase is quoted."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from pathfinder.tests._support.recorded_searches import suite_search

_TEXT = suite_search("search_genes_by_text")
_INFOS = format_param_info_typed(_TEXT.parameters or [])
_PHRASE_REQUEST = (
    "Please undo those changes: search the exact phrase in the product field "
    "only and drop the domain steps."
)


def _bind(message: str, term: str) -> str:
    """The term the call binds; a refusal raises instead."""
    call = CriterionCall(
        criterion_id="c_text",
        search_name="GenesByText",
        text="polar tube protein in the product field",
        params={"text_expression": term, "text_fields": ["product"]},
    )
    refuse_what_the_words_decide(_TEXT, call, _INFOS, ["Polar tube protein.", message])
    return term


def test_an_unquoted_term_the_request_asks_as_a_phrase_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_PHRASE_REQUEST, "polar tube protein")

    assert refused.value.message == (
        "text_expression on GenesByText: the request asks for the phrase, so "
        'the term is quoted: "polar tube protein"; an unquoted term matches any of '
        "its words."
    )


def test_the_quoted_term_binds() -> None:
    assert _bind(_PHRASE_REQUEST, '"polar tube protein"') == '"polar tube protein"'


def test_an_unquoted_term_binds_when_no_message_asks_for_the_phrase() -> None:
    assert _bind("Search the product field only.", "polar tube protein") == (
        "polar tube protein"
    )


@pytest.mark.parametrize(
    "message",
    [
        "Search it as a phrase.",
        "Put the term in quotes.",
        "Search for the phrase polar tube protein.",
    ],
)
def test_each_wording_asks_for_the_phrase(message: str) -> None:
    with pytest.raises(ModelRetry):
        _bind(message, "polar tube protein")
