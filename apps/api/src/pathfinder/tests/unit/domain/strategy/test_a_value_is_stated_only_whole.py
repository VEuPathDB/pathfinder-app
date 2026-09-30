"""A value is stated only when one researcher message holds all of its words
as a run; a number word reads as its digits."""

from __future__ import annotations

from typing import get_args

from veupathdb.domain.parameters import (
    FilterTermClause,
    FilterValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    from_wire,
)

from pathfinder.domain.strategy.value_source import (
    stated_run,
    stated_texts,
    value_source,
)

_GAL_TURN_1 = (
    "Entamoeba histolytica HM-1:IMSS genes annotated as Gal/GalNAc lectin subunits."
)
_GAL_TURN_2 = (
    "Only Igl1 and Igl2? The Gal/GalNAc lectin also has the heavy subunit (Hgl) "
    "and the light subunit (Lgl), and I expected those too. Can you include every "
    "subunit of the lectin?"
)
_GAL_TURN_4 = "Please update the search to it now."
_COMPOSED = (
    '("Gal/GalNAc lectin" OR Hgl OR Lgl OR Igl1 OR Igl2 OR ((large subunit OR '
    "small subunit) AND lectin AND galactose-inhibitable))"
)
_TM_REQUEST = (
    "Cryptosporidium parvum Iowa II genes with at least two transmembrane domains "
    "and no ortholog in Toxoplasma gondii."
)


def _source(value: ParamValue, texts: list[str]) -> str:
    return value_source(value, initial_display_value=None, request_texts=texts)


def test_a_boolean_the_model_composed_is_chosen() -> None:
    texts = [_GAL_TURN_1, _GAL_TURN_2, _GAL_TURN_4]

    assert _source(StringValue(value=_COMPOSED), texts) == "chosen"


def test_a_phrase_the_request_holds_only_in_another_form_is_chosen() -> None:
    quoted = StringValue(value='"Gal/GalNAc lectin subunit"')

    assert _source(quoted, [_GAL_TURN_1]) == "chosen"


def test_a_number_word_states_its_digit() -> None:
    assert (
        _source(NumberValue(value=2), [_TM_REQUEST]),
        stated_run(NumberValue(value=2), [_TM_REQUEST]),
    ) == ("stated", "two")


def test_a_number_the_request_never_names_is_chosen() -> None:
    assert _source(NumberValue(value=3), [_TM_REQUEST]) == "chosen"


def test_every_pick_of_a_multi_pick_is_stated_in_one_message() -> None:
    picks = MultiPickValue(
        values=["Cryptosporidium parvum Iowa II", "Toxoplasma gondii"]
    )

    assert [
        _source(picks, [_TM_REQUEST]),
        _source(picks, ["Cryptosporidium parvum Iowa II genes", "Toxoplasma gondii"]),
    ] == ["stated", "chosen"]


def test_a_range_is_stated_by_both_of_its_bounds() -> None:
    assert [
        _source(
            from_wire("number-range", '{"min": 2, "max": 5}'),
            ["between two and five domains"],
        ),
        _source(
            from_wire("number-range", '{"min": 2, "max": 6}'),
            ["between two and five domains"],
        ),
    ] == ["stated", "chosen"]


_SAMPLES: dict[ParamKind, ParamValue] = {
    "string": StringValue(value="kinase"),
    "number": NumberValue(value=2),
    "number-range": from_wire("number-range", '{"min": 2, "max": 5}'),
    "date": from_wire("date", "2020-01-01"),
    "date-range": from_wire("date-range", '{"min": "2020-01-01", "max": "2021-01-01"}'),
    "timestamp": from_wire("timestamp", "2020-01-01T00:00:00"),
    "single-pick-vocabulary": SinglePickValue(value="up-regulated"),
    "multi-pick-vocabulary": MultiPickValue(values=["product", "Notes"]),
    "filter": FilterValue(filters=[FilterTermClause(field="sex", value=["female"])]),
    "input-dataset": InputDatasetValue(dataset_id="12345"),
    "input-step": InputStepValue(step_id="step_1"),
}


def test_every_value_kind_has_a_source_rule() -> None:
    assert {kind: stated_texts(_SAMPLES[kind]) for kind in get_args(ParamKind)} == {
        "string": ["kinase"],
        "number": ["2"],
        "number-range": ["2", "5"],
        "date": ["2020-01-01"],
        "date-range": ["2020-01-01", "2021-01-01"],
        "timestamp": ["2020-01-01T00:00:00"],
        "single-pick-vocabulary": ["up-regulated"],
        "multi-pick-vocabulary": ["product", "Notes"],
        "filter": [],
        "input-dataset": [],
        "input-step": [],
    }


def test_a_value_no_researcher_writes_in_words_is_never_stated() -> None:
    step = InputStepValue(step_id="step_1")

    assert _source(step, ["use step 1"]) == "chosen"
