from __future__ import annotations

from typing import get_args

import pytest
from veupathdb.domain.parameters import (
    HeldValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    ParamKind,
    StringValue,
)

from strategist.domain.private_inputs import (
    OWNER_HANDLE_KINDS,
    PRIVATE_INPUT_KINDS,
    PUBLIC_INPUT_KINDS,
    ViewerInputs,
    inputs_for_viewer,
    is_account_dataset,
)

UPLOAD = "EDAUD_sF88g1cwo00gw"
CURATED = "DS_0ad509829e"


def test_every_parameter_kind_is_classed_once() -> None:
    kinds = set(get_args(ParamKind)) | {"held"}
    classes = (PRIVATE_INPUT_KINDS, OWNER_HANDLE_KINDS, PUBLIC_INPUT_KINDS)

    assert set[str]().union(*classes) == kinds
    assert sum(len(c) for c in classes) == len(kinds)


def test_a_dataset_input_is_withheld_without_the_account_reads() -> None:
    organism = MultiPickValue(values=["Plasmodium falciparum 3D7"])

    read = inputs_for_viewer(
        {
            "ds_gene_ids": InputDatasetValue(dataset_id="330713643"),
            "organism": organism,
        },
        include_account_reads=False,
    )

    assert read == ViewerInputs(shown={"organism": organism}, withheld=["ds_gene_ids"])


def test_a_dataset_input_is_kept_with_the_account_reads() -> None:
    value = InputDatasetValue(dataset_id="330713643")

    assert inputs_for_viewer(
        {"ds_gene_ids": value}, include_account_reads=True
    ) == ViewerInputs(shown={"ds_gene_ids": value}, withheld=[])


def test_a_held_value_is_withheld_since_its_kind_is_unknown() -> None:
    read = inputs_for_viewer(
        {"x": HeldValue(wire="330713643")}, include_account_reads=False
    )

    assert (read.shown, read.withheld) == ({}, ["x"])


@pytest.mark.parametrize("include_account_reads", [False, True])
def test_a_step_input_is_withheld_either_way(include_account_reads: bool) -> None:
    read = inputs_for_viewer(
        {"bq_input_step": InputStepValue(step_id="900117")},
        include_account_reads=include_account_reads,
    )

    assert (read.shown, read.withheld) == ({}, [])


def test_an_uploaded_study_is_account_data_and_a_curated_one_is_not() -> None:
    assert (is_account_dataset(UPLOAD), is_account_dataset(CURATED)) == (True, False)


def test_a_step_on_an_uploaded_study_withholds_its_inputs() -> None:
    read = inputs_for_viewer(
        {
            "eda_dataset_id": StringValue(value=UPLOAD),
            "eda_analysis_spec": StringValue(value='{"studyId": "x"}'),
        },
        include_account_reads=False,
    )

    assert (read.shown, read.withheld) == ({}, ["eda_analysis_spec", "eda_dataset_id"])


def test_a_step_on_a_curated_study_shows_its_inputs() -> None:
    dataset = StringValue(value=CURATED)

    read = inputs_for_viewer({"eda_dataset_id": dataset}, include_account_reads=False)

    assert read == ViewerInputs(shown={"eda_dataset_id": dataset}, withheld=[])


def test_a_step_on_an_uploaded_study_is_shown_with_the_account_reads() -> None:
    dataset = StringValue(value=UPLOAD)

    read = inputs_for_viewer({"eda_dataset_id": dataset}, include_account_reads=True)

    assert read == ViewerInputs(shown={"eda_dataset_id": dataset}, withheld=[])
