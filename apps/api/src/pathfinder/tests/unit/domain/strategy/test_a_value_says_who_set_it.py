"""Every bound value carries who set it: the request, the model, the site
default or a card, and the counts measured around it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import MultiPickValue, NumberValue, StringValue

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)
from pathfinder.domain.strategy.spec_replay import criterion_rebound, criterion_restated
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.domain.strategy.value_source import stated_run, value_source

from ._builders import text_leaf

_PERCENTILE = "min_expression_percentile"
_REQUEST = (
    "genes expressed in the top 10 percent of Plasmodium falciparum 3D7 blood stages"
)


def _criterion() -> Criterion:
    return Criterion(
        id="c_expr",
        text="expressed in blood stages",
        search_name="GenesByRNASeqPercentile",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                source="stated",
                basis="Plasmodium falciparum 3D7",
            ),
            _PERCENTILE: BoundValue(value=NumberValue(value=80), source="default"),
            "dataset": BoundValue(
                value=StringValue(value="pfal3D7_Blood"),
                source="chosen",
                basis="the only blood stage dataset",
            ),
        },
        measurements=[
            Measurement(kind="loosest_bound", param=_PERCENTILE, count=5120),
        ],
        result_count=1024,
    )


def test_the_defaulted_params_are_the_values_the_site_default_set() -> None:
    assert _criterion().defaulted() == [_PERCENTILE]


def test_the_param_values_are_the_bound_values_without_their_source() -> None:
    assert _criterion().param_values["dataset"] == StringValue(value="pfal3D7_Blood")


def test_the_step_parameters_carry_the_bound_values() -> None:
    assert _criterion().step_parameters[_PERCENTILE] == NumberValue(value=80)


def test_bind_values_gives_every_value_one_source() -> None:
    bound = bind_values({"organism": StringValue(value="Pf3D7")}, "stated", [], "held")

    assert bound == {
        "organism": BoundValue(
            value=StringValue(value="Pf3D7"), source="stated", basis="held"
        )
    }


def test_a_source_outside_the_four_is_refused() -> None:
    with pytest.raises(ValidationError):
        BoundValue.model_validate(
            {"value": {"type": "string", "value": "x"}, "source": "guessed"}
        )


def test_a_measurement_kind_outside_the_six_is_refused() -> None:
    with pytest.raises(ValidationError):
        Measurement.model_validate({"kind": "median", "param": _PERCENTILE})


def test_a_vocabulary_label_measurement_holds_no_count() -> None:
    label = Measurement(kind="vocabulary_label", param="go_term", label="membrane")

    assert (label.count, label.label) == (None, "membrane")


def test_a_restated_value_is_held_and_forgets_its_measurements() -> None:
    restated = criterion_restated(
        _criterion(), _PERCENTILE, NumberValue(value=90), sheet=()
    )

    assert (
        restated.resolved_params[_PERCENTILE].source,
        restated.defaulted(),
        restated.measurements,
    ) == ("held", [], [])


def test_a_rebound_search_forgets_every_measurement() -> None:
    assert criterion_rebound(_criterion(), text_leaf(), None).measurements == []


class TestTheSourceOfAValue:
    """The tool decides the source; the model never does."""

    def test_a_value_the_request_states_is_stated(self) -> None:
        assert (
            value_source(
                StringValue(value="blood stages"),
                placeholder=False,
                unset=False,
                request_texts=[_REQUEST],
            )
            == "stated"
        )

    def test_a_stated_value_at_the_default_is_stated(self) -> None:
        assert (
            value_source(
                StringValue(value="blood stages"),
                placeholder=False,
                unset=True,
                request_texts=[_REQUEST],
            )
            == "stated"
        )

    def test_a_value_an_answered_card_set_is_card(self) -> None:
        assert (
            value_source(
                NumberValue(value=50),
                placeholder=False,
                unset=False,
                request_texts=[_REQUEST],
                card_value="50",
            )
            == "card"
        )

    def test_a_card_on_another_value_does_not_set_this_one(self) -> None:
        assert (
            value_source(
                NumberValue(value=50),
                placeholder=False,
                unset=False,
                request_texts=[_REQUEST],
                card_value="60",
            )
            == "chosen"
        )

    def test_an_unstated_value_at_the_initial_display_value_is_default(self) -> None:
        assert (
            value_source(
                NumberValue(value=80),
                placeholder=False,
                unset=True,
                request_texts=[_REQUEST],
            )
            == "default"
        )

    def test_any_other_value_is_chosen(self) -> None:
        assert (
            value_source(
                StringValue(value="pfal3D7_Blood"),
                placeholder=False,
                unset=False,
                request_texts=[_REQUEST],
            )
            == "chosen"
        )

    def test_a_multi_word_value_is_stated_by_a_run_of_its_words(self) -> None:
        assert (
            value_source(
                MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                placeholder=False,
                unset=False,
                request_texts=["an earlier message", _REQUEST],
            )
            == "stated"
        )

    def test_the_stated_run_is_the_request_words_in_their_own_spelling(self) -> None:
        assert (
            stated_run(MultiPickValue(values=["plasmodium falciparum 3d7"]), [_REQUEST])
            == "Plasmodium falciparum 3D7"
        )
