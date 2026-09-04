"""The context each parameter-validation failure carries.

A spec failure serializes the whole parameter spec, so a caller can correct the
values without a second metadata read.
"""

from __future__ import annotations

from typing import Any, cast

from pathfinder.domain.parameters.specs import ParamSpecNormalized
from pathfinder.domain.parameters.wdk_vocab import WDKVocabTerm
from pathfinder.platform.errors import ValidationError
from pathfinder.services.catalog._param_validation_errors import (
    invalid_dependents_error,
    missing_params_error,
    unknown_params_error,
    unknown_search_error,
    unreadable_search_error,
    wdk_rejection_error,
)

_RECORD_TYPE = "transcript"
_SEARCH_NAME = "GenesByTaxon"


def _specs() -> dict[str, ParamSpecNormalized]:
    return {
        "organism": ParamSpecNormalized(
            name="organism",
            param_type="single-pick-vocabulary",
            dependent_params=("taxon",),
            vocabulary=[WDKVocabTerm(root=("Pf3D7", "Plasmodium falciparum", None))],
        ),
        "taxon": ParamSpecNormalized(
            name="taxon",
            param_type="single-pick-vocabulary",
            vocabulary=[WDKVocabTerm(root=("TaxonA", "Taxon A", None))],
        ),
    }


def _context(exc: ValidationError) -> dict[str, Any]:
    assert exc.errors is not None
    entry = cast("dict[str, Any]", exc.errors[0])
    return cast("dict[str, Any]", entry["context"])


class TestEveryPayloadNamesTheSearchAndItsSpec:
    def test_the_search_is_named(self) -> None:
        context = _context(
            missing_params_error(
                record_type=_RECORD_TYPE,
                search_name=_SEARCH_NAME,
                param_spec_map=_specs(),
                missing=["taxon"],
            )
        )

        assert context["recordType"] == _RECORD_TYPE
        assert context["searchName"] == _SEARCH_NAME

    def test_the_whole_parameter_spec_is_serialized(self) -> None:
        context = _context(
            missing_params_error(
                record_type=_RECORD_TYPE,
                search_name=_SEARCH_NAME,
                param_spec_map=_specs(),
                missing=["taxon"],
            )
        )

        assert [p["name"] for p in context["parameters"]] == ["organism", "taxon"]

    def test_only_the_failure_of_this_payload_is_present(self) -> None:
        context = _context(
            missing_params_error(
                record_type=_RECORD_TYPE,
                search_name=_SEARCH_NAME,
                param_spec_map=_specs(),
                missing=["taxon"],
            )
        )

        assert context["missing"] == ["taxon"]
        assert "unknown" not in context
        assert "invalidDependents" not in context


class TestUnknownParams:
    def test_the_names_are_reported(self) -> None:
        exc = unknown_params_error(
            record_type=_RECORD_TYPE,
            search_name=_SEARCH_NAME,
            param_spec_map=_specs(),
            unknown=["made_up"],
        )

        assert exc.title == "Unknown parameters provided"
        assert _context(exc)["unknown"] == ["made_up"]


class TestMissingParams:
    def test_the_title_lists_the_names(self) -> None:
        exc = missing_params_error(
            record_type=_RECORD_TYPE,
            search_name=_SEARCH_NAME,
            param_spec_map=_specs(),
            missing=["organism", "taxon"],
        )

        assert exc.title == "Missing required parameters: organism, taxon"


class TestInvalidDependents:
    def test_the_rejected_value_carries_its_post_refresh_vocabulary(self) -> None:
        exc = invalid_dependents_error(
            record_type=_RECORD_TYPE,
            search_name=_SEARCH_NAME,
            param_spec_map=_specs(),
            violations=[("taxon", ["TaxonB"])],
        )

        entry = _context(exc)["invalidDependents"][0]

        assert entry["name"] == "taxon"
        assert entry["values"] == ["TaxonB"]
        assert entry["validOptions"] == [{"value": "TaxonA", "display": "Taxon A"}]

    def test_the_title_names_every_rejected_value(self) -> None:
        exc = invalid_dependents_error(
            record_type=_RECORD_TYPE,
            search_name=_SEARCH_NAME,
            param_spec_map=_specs(),
            violations=[("taxon", ["TaxonB"])],
        )

        assert exc.title.startswith("Invalid dependent-parameter values: taxon=")

    def test_a_parameter_without_a_vocabulary_reports_no_options(self) -> None:
        specs = _specs()
        specs["taxon"] = ParamSpecNormalized(name="taxon", param_type="string")

        exc = invalid_dependents_error(
            record_type=_RECORD_TYPE,
            search_name=_SEARCH_NAME,
            param_spec_map=specs,
            violations=[("taxon", ["anything"])],
        )

        assert "validOptions" not in _context(exc)["invalidDependents"][0]


class TestUnknownSearch:
    def test_the_hint_is_reported_even_when_there_is_none(self) -> None:
        exc = unknown_search_error(
            search_name=_SEARCH_NAME, record_type=None, record_type_hint=None
        )

        assert exc.title == f"Unknown or invalid search: {_SEARCH_NAME}"
        assert exc.detail == "Search name not found in any record type."
        assert _context(exc) == {"recordType": None, "recordTypeHint": None}


class TestUnreadableSearch:
    def test_the_record_type_catalog_is_offered(self) -> None:
        exc = unreadable_search_error(
            search_name=_SEARCH_NAME,
            record_type=_RECORD_TYPE,
            detail="WDK said no",
            available_searches=["GenesByTaxon", "GenesByLocation"],
            record_type_hint=None,
        )

        assert exc.title == f"Unknown or invalid search: {_SEARCH_NAME}"
        assert exc.detail == "WDK said no"
        assert _context(exc) == {
            "recordType": _RECORD_TYPE,
            "availableSearches": ["GenesByTaxon", "GenesByLocation"],
            "recordTypeHint": None,
        }


class TestWdkRejection:
    def test_one_entry_per_rejected_parameter(self) -> None:
        exc = wdk_rejection_error(
            detail="organism: Cannot be empty.",
            by_key={"organism": ["Cannot be empty."]},
        )

        assert exc.title == "Invalid parameter value"
        assert exc.errors == [{"param": "organism", "messages": ["Cannot be empty."]}]

    def test_an_empty_verdict_still_says_wdk_refused(self) -> None:
        exc = wdk_rejection_error(detail="", by_key={})

        assert exc.detail == "WDK rejected these parameter values."
        assert exc.errors == []
