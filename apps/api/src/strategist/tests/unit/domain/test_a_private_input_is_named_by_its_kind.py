from __future__ import annotations

from typing import get_args

import pytest
from pydantic import JsonValue
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
    inputs_for_viewer,
)
from strategist.domain.strategy.step_rationale import (
    AnalysisRationale,
    ControlsRationale,
    SearchRationale,
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

    assert (read.shown, read.withheld) == ({"organism": organism}, ["ds_gene_ids"])


def test_a_dataset_input_is_kept_with_the_account_reads() -> None:
    value = InputDatasetValue(dataset_id="330713643")

    read = inputs_for_viewer({"ds_gene_ids": value}, include_account_reads=True)

    assert (read.shown, read.withheld) == ({"ds_gene_ids": value}, [])


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

    assert (read.shown, read.withheld) == ({"eda_dataset_id": dataset}, [])


def test_a_step_on_an_uploaded_study_is_shown_with_the_account_reads() -> None:
    dataset = StringValue(value=UPLOAD)

    read = inputs_for_viewer({"eda_dataset_id": dataset}, include_account_reads=True)

    assert (read.shown, read.withheld) == ({"eda_dataset_id": dataset}, [])


LIST_INPUTS = inputs_for_viewer(
    {
        "ds_gene_ids": InputDatasetValue(dataset_id="330713643"),
        "text_expression": StringValue(value="kinase"),
    },
    include_account_reads=False,
)


def _search(reason: str) -> SearchRationale:
    return SearchRationale(
        search_name="GeneByLocusTag",
        basis="parameter",
        term="Gene ID list",
        reason=reason,
        tool_call_id="c-1",
        derived_from={"ds_gene_ids": "330713643", "text_expression": "kinase"},
    )


def test_a_reason_that_quotes_a_withheld_input_is_cleared() -> None:
    reasons = ["It reads the saved list 330713643.", "Saved list 330713643, kinases."]

    assert [_search(r).for_viewer(LIST_INPUTS) for r in reasons] == [None, None]


def test_a_reason_keeps_only_the_inputs_the_viewer_reads() -> None:
    seen = _search("Kinases by name.").for_viewer(LIST_INPUTS)

    assert seen == _search("Kinases by name.").model_copy(
        update={"derived_from": {"text_expression": "kinase"}}
    )


@pytest.mark.parametrize(
    ("include_account_reads", "kept"), [(False, False), (True, True)]
)
def test_an_analysis_on_the_owners_upload_is_account_data(
    include_account_reads: bool, kept: bool
) -> None:
    upload = AnalysisRationale(
        dataset_id=UPLOAD, term="DESeq2", method="DESeq2", reason="Up in gametocytes."
    )
    inputs = inputs_for_viewer(
        {"eda_dataset_id": StringValue(value=UPLOAD)},
        include_account_reads=include_account_reads,
    )

    assert (upload.for_viewer(inputs) == upload) is kept


def test_an_analysis_on_a_curated_study_is_kept() -> None:
    curated = AnalysisRationale(dataset_id=CURATED, term="x", reason="Up.")

    assert curated.for_viewer(LIST_INPUTS) == curated


def test_a_controls_reason_that_quotes_a_withheld_input_is_cleared() -> None:
    controls = ControlsRationale(
        task_id="t-1",
        search_name="GeneByLocusTag",
        source="thread",
        basis="the saved list 330713643",
        informs="recovering",
        recovered=3,
        positives=4,
        admitted=1,
        negatives=9,
        result_size=41,
    )

    assert controls.for_viewer(LIST_INPUTS) is None
    assert controls.model_copy(update={"basis": "the thread"}).for_viewer(
        LIST_INPUTS
    ) == controls.model_copy(update={"basis": "the thread"})


def test_an_untyped_value_shows_only_with_the_account_reads_and_no_handle() -> None:
    owned = inputs_for_viewer(
        {"bq_input_step": InputStepValue(step_id="900117")}, include_account_reads=True
    )
    closed = inputs_for_viewer({}, include_account_reads=False)
    genes: JsonValue = {"ids": "PF3D7_0100100"}
    handle: JsonValue = {"step": "900117"}

    assert [
        owned.untyped(genes, withheld=None),
        owned.untyped(handle, withheld=None),
        closed.untyped(genes, withheld=None),
    ] == [genes, None, None]
