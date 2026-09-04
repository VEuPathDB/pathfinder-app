"""Hidden required parameters, the report of what was filled, and stale
dependent values.

WDK demands hidden required parameters and the model cannot see them, so their
declared defaults are supplied and named. A visible required parameter stays
the model's job: filling it masks genuinely missing input.
"""

from __future__ import annotations

from pathfinder.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_hidden_required_defaults,
    filled_hidden_defaults,
    find_dependent_value_violations,
    find_missing_required_params,
)
from pathfinder.domain.parameters.value_codec import to_decoded_map
from pathfinder.domain.parameters.values import SinglePickValue, StringValue
from pathfinder.domain.parameters.wdk_vocab import WDKVocabTerm


def _spec(
    name: str,
    *,
    visible: bool,
    default: str | None,
    allow_empty: bool = False,
) -> ParamSpecNormalized:
    return ParamSpecNormalized(
        name=name,
        param_type="string",
        is_visible=visible,
        allow_empty_value=allow_empty,
        initial_display_value=default,
    )


# ``document_type`` is hidden, required, and fixed to ``gene``. The model cannot
# see it, so it omits it, and the required-check then reports it missing.
_GENES_BY_TEXT = {
    "text_expression": _spec("text_expression", visible=True, default="*reductase"),
    "document_type": _spec("document_type", visible=False, default="gene"),
}

_PROFILE = {
    "organism": _spec("organism", visible=True, default="Pf3D7"),
    "channel": _spec("channel", visible=False, default="Channel 1"),
    "profile_pattern": _spec("profile_pattern", visible=False, default="hsap=1T"),
}


class TestTheFill:
    def test_hidden_required_param_is_filled_from_its_fixed_default(self) -> None:
        filled = fill_hidden_required_defaults(
            _GENES_BY_TEXT, {"text_expression": StringValue(value="kinase")}
        )

        assert filled == {
            "text_expression": StringValue(value="kinase"),
            "document_type": StringValue(value="gene"),
        }

    def test_visible_required_param_is_not_auto_filled(self) -> None:
        # A genuinely missing VISIBLE required param must not be silently filled
        # with the form-example default.
        filled = fill_hidden_required_defaults(_GENES_BY_TEXT, {})

        assert filled == {"document_type": StringValue(value="gene")}

    def test_filling_resolves_the_missing_required_contradiction(self) -> None:
        filled = fill_hidden_required_defaults(
            _GENES_BY_TEXT, {"text_expression": StringValue(value="kinase")}
        )

        assert (
            find_missing_required_params(_GENES_BY_TEXT, to_decoded_map(filled)) == []
        )

    def test_genuinely_missing_visible_param_still_reported(self) -> None:
        filled = fill_hidden_required_defaults(_GENES_BY_TEXT, {})

        assert find_missing_required_params(_GENES_BY_TEXT, to_decoded_map(filled)) == [
            "text_expression"
        ]


class TestTheFillIsNamed:
    def test_a_hidden_default_is_reported(self) -> None:
        assert filled_hidden_defaults(_PROFILE, {}) == ["channel", "profile_pattern"]

    def test_a_value_the_caller_supplied_is_not_reported(self) -> None:
        supplied = {"profile_pattern": SinglePickValue(value="%hsap:N%pfal:Y%")}

        assert filled_hidden_defaults(_PROFILE, supplied) == ["channel"]

    def test_a_visible_parameter_is_never_reported(self) -> None:
        # A visible default is the model's to see and choose.
        assert "organism" not in filled_hidden_defaults(_PROFILE, {})

    def test_nothing_to_fill_reports_nothing(self) -> None:
        supplied = {
            "channel": SinglePickValue(value="Channel 1"),
            "profile_pattern": SinglePickValue(value="%pfal:Y%"),
        }

        assert filled_hidden_defaults(_PROFILE, supplied) == []

    def test_a_hidden_param_with_no_default_is_not_reported(self) -> None:
        specs = {"secret": _spec("secret", visible=False, default=None)}

        assert filled_hidden_defaults(specs, {}) == []

    def test_a_hidden_param_that_allows_empty_is_not_reported(self) -> None:
        specs = {"opt": _spec("opt", visible=False, default="x", allow_empty=True)}

        assert filled_hidden_defaults(specs, {}) == []


class TestTheReportAgreesWithTheFill:
    def test_every_reported_name_was_actually_filled(self) -> None:
        filled = fill_hidden_required_defaults(_PROFILE, {})

        assert set(filled_hidden_defaults(_PROFILE, {})) <= set(filled)

    def test_the_report_matches_what_the_fill_added(self) -> None:
        before = {"channel": SinglePickValue(value="Channel 2")}
        filled = fill_hidden_required_defaults(_PROFILE, before)

        assert sorted(set(filled) - set(before)) == filled_hidden_defaults(
            _PROFILE, before
        )


def _vocab(*terms: str) -> list[WDKVocabTerm]:
    return [WDKVocabTerm(root=(t, t, None)) for t in terms]


def _dependent_specs(child_vocab: list[WDKVocabTerm]) -> dict[str, ParamSpecNormalized]:
    parent = ParamSpecNormalized(
        name="document_type",
        param_type="string",
        dependent_params=("text_fields",),
    )
    child = ParamSpecNormalized(
        name="text_fields",
        param_type="multi-pick-vocabulary",
        vocabulary=child_vocab,
    )
    return {"document_type": parent, "text_fields": child}


class TestDependentValueViolations:
    def test_stale_dependent_value_after_refresh_is_flagged(self) -> None:
        specs = _dependent_specs(_vocab("product", "name"))

        assert find_dependent_value_violations(
            specs, {"text_fields": ["was_valid"]}
        ) == [("text_fields", ["was_valid"])]

    def test_value_in_refreshed_vocab_is_not_flagged(self) -> None:
        specs = _dependent_specs(_vocab("product", "name"))

        assert (
            find_dependent_value_violations(specs, {"text_fields": ["product"]}) == []
        )

    def test_partial_stale_reports_only_the_bad_values(self) -> None:
        specs = _dependent_specs(_vocab("product", "name"))

        assert find_dependent_value_violations(
            specs, {"text_fields": ["product", "gone"]}
        ) == [("text_fields", ["gone"])]

    def test_empty_dependent_value_is_skipped(self) -> None:
        specs = _dependent_specs(_vocab("product"))

        assert find_dependent_value_violations(specs, {"text_fields": []}) == []

    def test_non_dependent_param_is_not_checked(self) -> None:
        solo = ParamSpecNormalized(
            name="solo", param_type="string", vocabulary=_vocab("only")
        )

        assert (
            find_dependent_value_violations({"solo": solo}, {"solo": "anything"}) == []
        )
