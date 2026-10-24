"""Each value of a typed answer is a statistic row in the display form its schema type gives it."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, JsonValue
from veupathdb_mcp.audit import GeneticCode

from pathfinder.ai import fact_sources
from pathfinder.ai.audit.check_tools import build_check_toolset
from pathfinder.domain.statistic_facts import (
    Identifier,
    Sentence,
    Share,
    StatisticRowFact,
)
from pathfinder.domain.statistic_rows import (
    NoDisplayFormError,
    fact_schema,
    model_rows,
    schema_rows,
)


class Verdict(StrEnum):
    SHIFTED = "UNSUPPORTED_SHIFTED"
    KEPT = "SUPPORTED"


class Junction(CamelModel):
    reads: int
    share: Share


class Answer(CamelModel):
    verdict: Verdict
    region: Literal["CDS", "UTR"]
    already_known: Literal["known", "not_searched"]
    frame_kept: bool
    junctions: list[Junction]
    transcript: str
    genome: str
    cause: Sentence | None
    span: tuple[int, int]
    code: GeneticCode


class Loose(CamelModel):
    payload: dict[str, JsonValue]


_ANSWER = Answer(
    verdict=Verdict.SHIFTED,
    region="CDS",
    already_known="not_searched",
    frame_kept=False,
    junctions=[Junction(reads=1226, share=0.889)],
    transcript="PcyM_0736700-t36_1",
    genome="Examplea alpha",
    cause=None,
    span=(4793693, 4793790),
    code=GeneticCode.CTG_SERINE,
)


def test_each_value_renders_in_the_form_its_type_gives_it() -> None:
    assert model_rows(_ANSWER) == [
        StatisticRowFact(
            name="verdict",
            value="unsupported shifted",
            form="word",
            code="UNSUPPORTED_SHIFTED",
        ),
        StatisticRowFact(name="region", value="CDS", form="word", code="CDS"),
        StatisticRowFact(
            name="alreadyKnown", value="not searched", form="word", code="not_searched"
        ),
        StatisticRowFact(name="frameKept", value="no", form="word"),
        StatisticRowFact(name="junctions.0.reads", value="1,226"),
        StatisticRowFact(name="junctions.0.share", value="88.9%"),
        StatisticRowFact(name="transcript", value="PcyM_0736700-t36_1", form="word"),
        StatisticRowFact(name="genome", value="Examplea alpha", form="word"),
        StatisticRowFact(name="span.0", value="4,793,693"),
        StatisticRowFact(name="span.1", value="4,793,790"),
        StatisticRowFact(
            name="code", value="CTG read as serine", form="word", code="ctg_serine"
        ),
    ]


def test_a_sentence_is_a_marked_field_and_any_other_string_a_word() -> None:
    rows = schema_rows(
        Answer,
        {"genome": "Plasmodium yoelii yoelii 17X", "cause": "The intron is unread."},
    )

    assert [(row.name, row.form) for row in rows] == [
        ("genome", "word"),
        ("cause", "sentence"),
    ]


def test_a_prefix_names_the_rows_under_it() -> None:
    names = [row.name for row in model_rows(Junction(reads=3, share=1.0), "runs.2")]

    assert names == ["runs.2.reads", "runs.2.share"]


def test_a_note_names_the_field_and_the_field_that_holds_it() -> None:
    rows = {row.name: row for row in model_rows(_ANSWER)}

    assert (
        rows["frameKept"].note(),
        rows["junctions.0.reads"].note(),
    ) == ("frame kept: no", "junctions reads: 1,226")


def test_a_key_the_schema_does_not_hold_still_renders() -> None:
    rows = schema_rows(Answer, {"frameKept": True, "added": "two words", "count": 3})

    assert rows == [
        StatisticRowFact(name="frameKept", value="yes", form="word"),
        StatisticRowFact(name="added", value="two words", form="word"),
        StatisticRowFact(name="count", value="3"),
    ]


def test_a_leaf_with_no_display_form_is_refused() -> None:
    with pytest.raises(NoDisplayFormError) as refused:
        fact_schema(Loose)

    assert str(refused.value) == "payload.*: no display form for the schema {}"


def test_a_toolset_with_an_answer_of_no_display_form_is_refused_when_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fact_sources, "FACT_SOURCES", (Loose,))

    with pytest.raises(NoDisplayFormError) as refused:
        build_check_toolset()

    assert str(refused.value) == "payload.*: no display form for the schema {}"


class Marked(CamelModel):
    reason: str = Field(json_schema_extra={"format": "sentence"})


def test_a_field_the_library_marks_through_its_schema_is_a_sentence() -> None:
    assert model_rows(Marked(reason="No junction track was read.")) == [
        StatisticRowFact(
            name="reason", value="No junction track was read.", form="sentence"
        )
    ]


class Counted(CamelModel):
    id: Identifier
    groups: int
    few: int
    edge: int
    mean: float
    low: float


def test_a_number_of_a_thousand_or_more_is_separated_and_an_id_is_not() -> None:
    rows = model_rows(
        Counted(id=52_314, groups=7364, few=999, edge=1000, mean=1234.5, low=999.5)
    )

    assert [(row.name, row.value) for row in rows] == [
        ("id", "52314"),
        ("groups", "7,364"),
        ("few", "999"),
        ("edge", "1,000"),
        ("mean", "1,234.5"),
        ("low", "999.5"),
    ]
