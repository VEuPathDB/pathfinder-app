"""The two WDK parameters, and the equality the bridge plugin requires."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.eda import EdaStringSetFilter
from veupathdb_mcp.catalog import (
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    EdaStepRequest,
)

from pathfinder.services.eda.authoring import new_analysis, serialize_spec


def _spec(dataset_id: str) -> str:
    return serialize_spec(
        new_analysis(
            dataset_id=dataset_id,
            display_name="x",
            filters=[
                EdaStringSetFilter(entity_id="E", variable_id="V", string_set=["a"])
            ],
        )
    )


def test_a_matching_dataset_id_is_accepted() -> None:
    request = EdaStepRequest(
        eda_dataset_id="DS_53f554ec6a", eda_analysis_spec=_spec("DS_53f554ec6a")
    )
    assert request.eda_dataset_id == "DS_53f554ec6a"


def test_a_mismatched_dataset_id_is_refused_before_wdk_sees_it() -> None:
    """The plugin requires spec.studyId to equal eda_dataset_id."""
    with pytest.raises(ValidationError) as excinfo:
        EdaStepRequest(
            eda_dataset_id="DS_66f9e70b8a", eda_analysis_spec=_spec("DS_53f554ec6a")
        )
    message = str(excinfo.value)
    assert "DS_66f9e70b8a" in message
    assert "DS_53f554ec6a" in message


def test_an_empty_spec_is_accepted_and_means_no_filters() -> None:
    request = EdaStepRequest(eda_dataset_id="DS_x", eda_analysis_spec="")
    assert request.eda_analysis_spec == ""


def test_a_study_id_in_the_spec_is_refused_because_both_are_dataset_ids() -> None:
    with pytest.raises(ValidationError) as excinfo:
        EdaStepRequest(
            eda_dataset_id="DS_e973eadd57",
            eda_analysis_spec=_spec("STUDY_e973eadd57"),
        )
    assert "dataset id" in str(excinfo.value)


def test_the_wdk_parameters_are_the_two_names_the_searches_declare() -> None:
    request = EdaStepRequest(
        eda_dataset_id="DS_53f554ec6a", eda_analysis_spec=_spec("DS_53f554ec6a")
    )
    params = request.wdk_parameters()
    assert set(params) == {EDA_DATASET_ID_PARAM, EDA_ANALYSIS_SPEC_PARAM}
    assert params[EDA_DATASET_ID_PARAM] == "DS_53f554ec6a"
    assert params[EDA_ANALYSIS_SPEC_PARAM] == _spec("DS_53f554ec6a")


def test_unparseable_spec_json_is_refused() -> None:
    with pytest.raises(ValidationError):
        EdaStepRequest(eda_dataset_id="DS_x", eda_analysis_spec="{not json")
