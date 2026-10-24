"""Each value of a typed answer is a statistic row in the display form its schema type gives it."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import JsonValue

from pathfinder.domain.statistic_facts import StatisticRowFact
from pathfinder.domain.statistic_rows import (
    NoDisplayFormError,
    fact_schema,
    model_rows,
)


class Verdict(StrEnum):
    SHIFTED = "UNSUPPORTED_SHIFTED"
    KEPT = "SUPPORTED"


class Junction(CamelModel):
    reads: int
    share: float


class Answer(CamelModel):
    verdict: Verdict
    certainty: Literal["high", "medium", "low"]
    already_known: Literal["known", "not_searched"]
    frame_kept: bool
    junctions: list[Junction]
    transcript: str
    genome: str
    cause: str | None
    span: tuple[int, int]


class Loose(CamelModel):
    payload: dict[str, JsonValue]


_ANSWER = Answer(
    verdict=Verdict.SHIFTED,
    certainty="high",
    already_known="not_searched",
    frame_kept=False,
    junctions=[Junction(reads=1226, share=0.25)],
    transcript="PcyM_0736700-t36_1",
    genome="Plasmodium cynomolgi strain M",
    cause=None,
    span=(4793693, 4793790),
)


def test_each_value_renders_in_the_form_its_type_gives_it() -> None:
    assert model_rows(_ANSWER) == [
        StatisticRowFact(name="verdict", value="unsupported shifted", form="word"),
        StatisticRowFact(name="certainty", value="high", form="word"),
        StatisticRowFact(name="alreadyKnown", value="not searched", form="word"),
        StatisticRowFact(name="frameKept", value="no", form="word"),
        StatisticRowFact(name="junctions.0.reads", value="1226"),
        StatisticRowFact(name="junctions.0.share", value="0.25"),
        StatisticRowFact(name="transcript", value="PcyM_0736700-t36_1"),
        StatisticRowFact(
            name="genome", value="Plasmodium cynomolgi strain M", form="word"
        ),
        StatisticRowFact(name="span.0", value="4793693"),
        StatisticRowFact(name="span.1", value="4793790"),
    ]


def test_a_prefix_names_the_rows_under_it() -> None:
    names = [row.name for row in model_rows(Junction(reads=3, share=1.0), "runs.2")]

    assert names == ["runs.2.reads", "runs.2.share"]


def test_a_word_row_is_noted_with_the_words_of_its_field() -> None:
    rows = {row.name: row for row in model_rows(_ANSWER)}

    assert (rows["frameKept"].note(), rows["alreadyKnown"].note()) == (
        "frame kept: no",
        "already known: not searched",
    )


def test_the_schema_names_the_display_kind_of_every_leaf() -> None:
    assert fact_schema(Answer).leaves == (
        ("verdict", "words"),
        ("certainty", "words"),
        ("alreadyKnown", "words"),
        ("frameKept", "boolean"),
        ("junctions.*.reads", "number"),
        ("junctions.*.share", "number"),
        ("transcript", "string"),
        ("genome", "string"),
        ("cause", "string"),
        ("span.*", "number"),
        ("span.*", "number"),
    )


def test_a_leaf_with_no_display_form_is_refused() -> None:
    with pytest.raises(NoDisplayFormError) as refused:
        fact_schema(Loose)

    assert str(refused.value) == "payload.*: no display form for the schema {}"
