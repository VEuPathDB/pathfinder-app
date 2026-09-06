"""The EDA service refusals carry the HTTP status the transport answers with."""

from __future__ import annotations

from veupathdb.errors import ValidationError

from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.eda.authoring import SubsetRejectedError
from pathfinder.services.eda.catalog import UnknownEdaDatasetError


def test_an_unknown_dataset_is_a_404_naming_the_dataset() -> None:
    error = UnknownEdaDatasetError("DS_nope", ["DS_a", "DS_b"])

    assert isinstance(error, NotFoundError)
    assert error.status == 404
    assert error.code is ErrorCode.NOT_FOUND
    assert error.dataset_id == "DS_nope"
    assert "DS_nope" in str(error)
    assert error.detail == error.guidance


def test_a_rejected_subset_is_a_422_carrying_one_row_per_message() -> None:
    error = SubsetRejectedError(
        ["'P. vivax' is not a value of Species.", "min is above max."]
    )

    assert isinstance(error, ValidationError)
    assert error.status == 422
    assert error.messages == [
        "'P. vivax' is not a value of Species.",
        "min is above max.",
    ]
    assert error.errors == [
        {"message": "'P. vivax' is not a value of Species."},
        {"message": "min is above max."},
    ]
    assert "P. vivax" in str(error)
