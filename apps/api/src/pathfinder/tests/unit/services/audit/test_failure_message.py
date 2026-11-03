from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pydantic
import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import ProgrammingError
from veupathdb.errors import (
    DataParsingError,
    ExternalServiceError,
    ValidationError,
    WDKError,
)
from veupathdb.jbrowse import JBrowseError
from veupathdb.wdk import wdk_failure
from veupathdb_mcp.audit import GeneRow

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.stages import RunStages
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.services.audit import confirm, screen
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.units import failure_message

_SITE = "plasmodb"
_SECRET = "api_key=held-in-the-query"
_URL = f"https://qa.plasmodb.org/plasmo.qa/service/answer?{_SECRET}"
_BODY = "<html>java.lang.NullPointerException at org.gusdb.wdk.Secret</html>"
_GENERIC = "An internal error occurred"


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _URL)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"Client error '{status}' for url '{_URL}'", request=request, response=response
    )


def _validation_error() -> pydantic.ValidationError:
    try:
        pydantic.TypeAdapter(int).validate_python(_SECRET)
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError


def _wdk_body(status: int = 404) -> WDKError:
    return wdk_failure("GET", f"/answer?{_SECRET}", status, _BODY)


def _wrapped(status: int) -> WDKError:
    error = _wdk_body(status)
    error.__cause__ = _status_error(status)
    return error


def _unanswered() -> WDKError:
    error = WDKError(f"GET {_URL} failed: no route", status=502)
    error.__cause__ = httpx.ConnectError(f"no route to {_URL}")
    return error


def _tool_error(cause: Exception) -> ToolError:
    error = ToolError(f"plasmodb read failed: {cause}")
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("cause", "stated"),
    [
        (_status_error(404), "plasmodb answered 404 to the audit reads"),
        (_wdk_body(404), "plasmodb answered 404 to the audit reads"),
        (_wrapped(403), "plasmodb answered 403 to the audit reads"),
        (
            httpx.ConnectError(f"no route to {_URL}"),
            "plasmodb did not answer the audit reads",
        ),
        (_unanswered(), "plasmodb did not answer the audit reads"),
        (JBrowseError("GET", _URL, 503), "plasmodb answered 503 to the audit reads"),
    ],
)
def test_a_tool_error_over_a_site_failure_states_a_fixed_sentence(
    cause: Exception, stated: str
) -> None:
    assert failure_message(_tool_error(cause), _SITE) == stated


@pytest.mark.parametrize(
    ("error", "stated"),
    [
        (_wdk_body(404), "WDKError: the site refused with 404"),
        (_wdk_body(502), "WDKError: the site answered 502"),
        (
            ExternalServiceError("VEuPathDB OAuth", f"read {_URL}", status=503),
            "ExternalServiceError: the site answered 503",
        ),
        (JBrowseError("GET", _URL, 503), "JBrowseError: the site answered 503"),
    ],
)
def test_a_site_refusal_states_its_type_and_status(
    error: Exception, stated: str
) -> None:
    assert failure_message(error, _SITE) == stated


@pytest.mark.parametrize("cause", [None, "pydantic"])
def test_a_parsing_failure_always_states_the_fixed_sentence(cause: str | None) -> None:
    error = DataParsingError(f"Unexpected answer: {_SECRET}")
    error.__cause__ = None if cause is None else _validation_error()
    assert failure_message(error, _SITE) == (
        "DataParsingError: the site's answer could not be read"
    )


@pytest.mark.parametrize(
    "error",
    [
        _status_error(404),
        httpx.ConnectError(f"no route to {_URL}"),
        _validation_error(),
    ],
)
def test_any_other_exception_states_its_type_alone(error: Exception) -> None:
    assert _SECRET in str(error)
    assert failure_message(error, _SITE) == f"{type(error).__name__}: {_GENERIC}"


def test_a_refusal_written_by_us_keeps_its_title_and_detail() -> None:
    refusal = ValidationError(title="Search refused", detail="the organism is unknown")
    assert failure_message(refusal, _SITE) == (
        "ValidationError: Search refused: the organism is unknown"
    )


def test_a_tool_refusal_with_no_cause_keeps_its_words() -> None:
    assert failure_message(ToolError("the check takes one gene"), _SITE) == (
        "the check takes one gene"
    )


def _parsed() -> int:
    return int(_SECRET)


def _raised_from_none() -> None:
    try:
        _parsed()
    except ValueError:
        msg = "half the circle"
        raise ToolError(msg) from None


def test_a_tool_refusal_raised_from_none_keeps_its_words() -> None:
    with pytest.raises(ToolError) as refused:
        _raised_from_none()
    assert isinstance(refused.value.__context__, ValueError)
    assert failure_message(refused.value, _SITE) == "half the circle"


def test_a_tool_error_over_a_value_error_states_the_check_failed() -> None:
    refused = ToolError(f"read failed: {_URL}")
    refused.__cause__ = ValueError(f"upstream said {_URL}")
    assert failure_message(refused, _SITE) == "the check failed"


def test_a_tool_error_over_a_parsing_failure_states_the_check_failed() -> None:
    refused = ToolError("served 10 records of 12")
    refused.__cause__ = DataParsingError("served 10 records of 12")
    assert failure_message(refused, _SITE) == "the check failed"


def test_a_tool_error_over_a_validation_error_quotes_no_input() -> None:
    refused = ToolError(f"read failed: {_SECRET}")
    refused.__cause__ = _validation_error()
    assert failure_message(refused, _SITE) == "the check failed"


def test_a_context_chain_with_no_cause_states_the_site_sentence() -> None:
    refused = ToolError(f"read failed: {_URL}")
    refused.__context__ = httpx.ConnectError(f"no route to {_URL}")
    assert refused.__cause__ is None
    assert failure_message(refused, _SITE) == (
        "plasmodb did not answer the audit reads"
    )


def test_a_status_deep_in_the_chain_names_the_site_sentence() -> None:
    middle = ValueError("wrapped")
    middle.__cause__ = _wdk_body(404)
    refused = ToolError(f"read failed: {_URL}")
    refused.__cause__ = middle
    assert failure_message(refused, _SITE) == "plasmodb answered 404 to the audit reads"


def test_a_tool_error_in_a_chain_that_loops_still_states_a_sentence() -> None:
    first = ValueError("one")
    second = ValueError("two")
    first.__cause__ = second
    second.__cause__ = first
    refused = ToolError("x")
    refused.__cause__ = first
    assert failure_message(refused, _SITE) == "the check failed"


def test_the_sql_of_a_database_error_is_not_stored() -> None:
    error = ProgrammingError("SELECT token FROM audit_runs", {}, Exception("gone"))
    assert failure_message(error, _SITE) == f"ProgrammingError: {_GENERIC}"


async def test_a_message_the_check_wrote_keeps_its_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_rows(site_id: str, genes: list[str]) -> list[GeneRow]:
        del site_id, genes
        return []

    monkeypatch.setattr(confirm, "record_rows", no_rows)
    assert await confirm._organisms("plasmodb", ["PF3D7_X"]) == UnitFailure(
        status="failed", message="plasmodb serves no gene row for PF3D7_X"
    )


async def test_a_gene_list_read_that_fails_holds_only_its_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gene_list(site_id: str, genes: list[str]) -> list[GeneRow]:
        del site_id, genes
        raise _status_error(404)

    monkeypatch.setattr(screen, "read_gene_list", gene_list)
    run = AuditRunRecord(
        id=uuid4(),
        user_id=uuid4(),
        conversation_id=None,
        site_id="plasmodb",
        release=None,
        scope=AuditScope(
            site_id="plasmodb",
            targets=(SingleGeneTarget(check="gene_length", genes=("PF3D7_X",)),),
        ),
        seed=1,
        status="running",
        stages=RunStages(),
        deadline_at=None,
        review=None,
        synthesis=None,
        created_at=datetime.now(UTC),
        finished_at=None,
    )
    assert await screen._target_rows(run, ["PF3D7_X"]) == UnitFailure(
        status="failed", message=f"HTTPStatusError: {_GENERIC}"
    )
