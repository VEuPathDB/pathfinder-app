"""An unquoted several-word text matches any of its words, so it is counted
again with each operand quoted as a phrase, whoever wrote it."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.caveats import PhraseCaveat, phrase_caveats
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.recorded_counts import serve_counts, wire
from pathfinder.tests._support.recorded_searches import suite_search

_TEXT = suite_search("search_genes_by_text")
# VectorBase GenesByText over product in Anopheles gambiae PEST, read live:
# the unquoted words count 158 genes, the quoted phrase 114.
_WORDS, _PHRASE = 158, 114


def _params(expression: str) -> dict[str, ParamValue]:
    return {
        "text_expression": StringValue(value=expression),
        "text_search_organism": MultiPickValue(values=["Anopheles gambiae PEST"]),
        "text_fields": MultiPickValue(values=["product"]),
    }


def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
    return _PHRASE if wire(params, "text_expression").startswith('"') else _WORDS


async def _measure(expression: str) -> list[Measurement]:
    params = _params(expression)
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="vectorbase",
            record_type="transcript",
            search_name="GenesByText",
            params=params,
            count=_WORDS,
            organism_param="text_search_organism",
        ),
        values={
            name: BoundValue(value=value, source="stated")
            for name, value in params.items()
        },
        infos=format_param_info_typed(list(_TEXT.parameters or [])),
    )


@pytest.mark.asyncio
async def test_a_stated_unquoted_phrase_is_counted_as_one_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _count)

    measured = await _measure("cytochrome P450")

    assert (asked, measured) == (
        ["GenesByText"],
        [
            Measurement(
                kind="wildcard_phrase",
                param="text_expression",
                count=_PHRASE,
                reading='"cytochrome P450"',
            )
        ],
    )


@pytest.mark.asyncio
async def test_a_quoted_or_single_word_stated_text_is_not_counted_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _count)

    assert (await _measure('"cytochrome P450"'), await _measure("P450"), asked) == (
        [],
        [],
        [],
    )


def test_the_two_counts_are_a_caveat() -> None:
    spec = OperationalSpec(
        goal="P450 genes",
        criteria=[
            Criterion(
                id="c_p450",
                text="cytochrome P450 family members",
                search_name="GenesByText",
                resolved_params=bound(
                    {"text_expression": StringValue(value="cytochrome P450")}
                ),
                param_display_names={"text_expression": "Text term"},
                measurements=[
                    Measurement(
                        kind="wildcard_phrase",
                        param="text_expression",
                        count=_PHRASE,
                        reading='"cytochrome P450"',
                    )
                ],
                result_count=_WORDS,
            )
        ],
    )

    [caveat] = phrase_caveats(spec)

    assert caveat == PhraseCaveat(
        criterion_id="c_p450",
        param_display_name="Text term",
        value="cytochrome P450",
        words_count=_WORDS,
        phrase_count=_PHRASE,
    )
    assert caveat.sentence == (
        "Text term 'cytochrome P450' matches any of its words: 158 genes; as "
        'the phrase "cytochrome P450": 114 genes'
    )


# GiardiaDB GenesByText over product and Products in Giardia Assemblage A
# isolate WB, read live: the unquoted words, and each operand as a phrase.
_VSP_WORDS, _VSP_PHRASES = 7131, 261
_VSP_EXPRESSION = "variant-specific surface protein OR VSP"


def _vsp_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    texts = {'"variant-specific surface protein" OR VSP': _VSP_PHRASES}
    return texts.get(wire(params, "text_expression"), 0)


@pytest.mark.asyncio
async def test_an_operator_word_stays_outside_the_quoted_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _vsp_count)

    measured = await _measure(_VSP_EXPRESSION)

    assert measured == [
        Measurement(
            kind="wildcard_phrase",
            param="text_expression",
            count=_VSP_PHRASES,
            reading='"variant-specific surface protein" OR VSP',
        )
    ]


@pytest.mark.asyncio
async def test_operands_of_one_word_have_no_phrase_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _vsp_count)

    assert (await _measure("VSP OR VSG"), asked) == ([], [])
