from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pydantic
import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import ProgrammingError
from veupathdb.errors import WDKError
from veupathdb_mcp.audit import GeneRow

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.stages import RunStages
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.services.audit import confirm, screen
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.units import failure_message

_SECRET = "api_key=held-in-the-query"
_URL = f"https://qa.plasmodb.org/plasmo.qa/service/answer?{_SECRET}"
_GENERIC = "An internal error occurred"


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _URL)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"{status} for {_URL}", request=request, response=response
    )


def _validation_error() -> pydantic.ValidationError:
    try:
        pydantic.TypeAdapter(int).validate_python(_SECRET)
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError


@pytest.mark.parametrize(
    "error",
    [
        _status_error(404),
        _status_error(502),
        httpx.ConnectError(f"no route to {_URL}"),
        _validation_error(),
    ],
)
def test_an_exceptions_text_is_never_the_stored_message(error: Exception) -> None:
    assert _SECRET in str(error)
    assert failure_message(error) == f"{type(error).__name__}: {_GENERIC}"


def test_a_refusal_keeps_its_words() -> None:
    refusal = WDKError("the organism is unknown", status=404)
    assert failure_message(refusal) == f"WDKError: {refusal}"


@pytest.mark.parametrize("cause", [None, ValueError("half the circle")])
def test_a_tool_refusal_keeps_its_own_words(cause: Exception | None) -> None:
    refused = ToolError("the check takes one gene")
    refused.__cause__ = cause
    assert failure_message(refused) == "the check takes one gene"


def test_the_sql_of_a_database_error_is_not_stored() -> None:
    error = ProgrammingError("SELECT token FROM audit_runs", {}, Exception("gone"))
    assert failure_message(error) == f"ProgrammingError: {_GENERIC}"


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
