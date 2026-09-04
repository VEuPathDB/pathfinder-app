from __future__ import annotations

import pytest

from pathfinder.integrations.eda.errors import (
    EdaBadRequestError,
    EdaComputeNotReadyError,
    EdaForbiddenError,
    EdaInvalidInputError,
    EdaNotFoundError,
    EdaServerError,
    eda_failure,
)
from pathfinder.platform.errors import AppError

_NOT_READY_BODY = (
    '{"status":"bad-request",'
    '"message":"Compute results are not available for the requested job."}'
)


def test_400_becomes_a_bad_request_carrying_the_service_message() -> None:
    error = eda_failure(
        "POST",
        "/studies/S/entities/E/count",
        400,
        '{"status":"bad-request","message":"Variable \'VAR_deadbeef\' is not found"}',
    )
    assert isinstance(error, EdaBadRequestError)
    assert error.status == 400
    assert error.detail is not None
    assert "VAR_deadbeef" in error.detail


def test_the_compute_not_ready_400_is_its_own_class() -> None:
    error = eda_failure(
        "POST",
        "/apps/differentialexpression/visualizations/volcanoplot",
        400,
        _NOT_READY_BODY,
    )
    assert isinstance(error, EdaComputeNotReadyError)
    assert type(error) is EdaComputeNotReadyError


def test_the_compute_not_ready_refusal_carries_409() -> None:
    """A pending compute is a state conflict, not a malformed request."""
    error = eda_failure(
        "POST",
        "/apps/differentialexpression/visualizations/volcanoplot",
        400,
        _NOT_READY_BODY,
    )
    assert error.status == 409


def test_422_names_the_offending_key() -> None:
    error = eda_failure(
        "POST",
        "/computes/differentialexpression",
        422,
        '{"status":"invalid-input","errors":{"general":[],"byKey":'
        '{"config":["Cannot deserialize value of type ... DESeq2"]}}}',
    )
    assert isinstance(error, EdaInvalidInputError)
    assert error.status == 422
    assert error.errors is not None
    assert error.errors == [
        {"key": "config", "messages": ["Cannot deserialize value of type ... DESeq2"]}
    ]


def test_403_is_forbidden_and_names_the_study_id_trap() -> None:
    error = eda_failure(
        "POST", "/computes/differentialexpression", 403, '{"status":"forbidden"}'
    )
    assert isinstance(error, EdaForbiddenError)
    assert error.detail is not None
    assert "STUDY_" in error.detail


def test_403_on_a_user_path_names_the_account_the_analysis_belongs_to() -> None:
    """An analysis under another account is not a study-id mistake."""
    error = eda_failure("GET", "/users/1202189953/analyses/PlasmoDB/Vd6RDIz", 403, "")
    assert isinstance(error, EdaForbiddenError)
    assert error.detail is not None
    assert (
        "The analysis belongs to a different VEuPathDB account than the one "
        "signed in now. Open the study again to create one under this account."
    ) in error.detail
    assert "STUDY_" not in error.detail


def test_404_and_500_map_to_their_own_classes() -> None:
    not_found = eda_failure("GET", "/jobs/x", 404, "")
    server = eda_failure(
        "POST",
        "/studies/S/entities/E/count",
        500,
        '{"status":"server-error","message":"Can\'t parse date/time string: 2017-05-05"}',
    )
    assert isinstance(not_found, EdaNotFoundError)
    assert isinstance(server, EdaServerError)
    assert (not_found.status, server.status) == (404, 500)


def test_an_unmapped_status_still_raises_an_eda_error() -> None:
    error = eda_failure("GET", "/studies", 418, "")
    assert error.status == 418


@pytest.mark.parametrize("status", [400, 403, 404, 422, 500])
def test_every_eda_error_is_an_app_error(status: int) -> None:
    error = eda_failure("GET", "/x", status, "")
    assert isinstance(error, AppError)
    assert error.status == status
