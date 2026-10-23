from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastmcp.exceptions import ToolError
from pydantic_ai import ToolFailed
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from veupathdb.errors import DataParsingError, ValidationError, WDKError
from veupathdb.jbrowse import GenomeIndexError, JBrowseError, TrackReadError

from pathfinder.ai.capabilities.site_reads import SiteReadFailures

_TOOL = "audit_gene_length"


async def _judged(error: Exception) -> str:
    capability = SiteReadFailures[Any](reads=frozenset({_TOOL}))
    with pytest.raises(ToolFailed) as failed:
        await capability.on_tool_execute_error(
            MagicMock(),
            call=ToolCallPart(tool_name=_TOOL, args={}, tool_call_id="tc"),
            tool_def=ToolDefinition(name=_TOOL, parameters_json_schema={}),
            args={},
            error=error,
        )
    return str(failed.value)


def _caused(text: str, cause: BaseException) -> ToolError:
    error = ToolError(text)
    error.__cause__ = cause
    return error


async def test_a_tool_error_with_no_cause_is_a_refusal() -> None:
    said = await _judged(ToolError("EXA_9999 names no gene of plasmodb"))

    assert said == (
        "The site refused audit_gene_length (EXA_9999 names no gene of plasmodb). "
        "Nothing was read and the strategy is unchanged. Correct the arguments the "
        "site names, or say that the site refused this read."
    )


async def test_a_tool_error_over_a_broken_connection_is_an_outage() -> None:
    said = await _judged(
        _caused("plasmodb did not answer the audit reads", httpx.ConnectError(""))
    )

    assert said.startswith(
        "audit_gene_length got no answer from the site (plasmodb did not answer "
        "the audit reads)."
    )


async def test_a_tool_error_over_a_site_refusal_is_a_refusal() -> None:
    said = await _judged(
        _caused("plasmodb answered 404 to the audit reads", WDKError("no", status=404))
    )

    assert said.startswith(
        "The site refused audit_gene_length (plasmodb answered 404 to the audit reads)."
    )


async def test_a_tool_error_over_a_sign_in_refusal_reaches_the_turn() -> None:
    error = _caused("login required", WDKError("login required", status=401))
    capability = SiteReadFailures[Any](reads=frozenset({_TOOL}))

    with pytest.raises(ToolError):
        await capability.on_tool_execute_error(
            MagicMock(),
            call=ToolCallPart(tool_name=_TOOL, args={}, tool_call_id="tc"),
            tool_def=ToolDefinition(name=_TOOL, parameters_json_schema={}),
            args={},
            error=error,
        )


async def test_a_tool_error_over_a_genome_store_failure_is_an_outage() -> None:
    said = await _judged(
        _caused(
            "plasmodb answered 503 to the audit reads",
            JBrowseError("GET", "https://example.org/seq", 503),
        )
    )

    assert said.startswith(
        "audit_gene_length got no answer from the site (plasmodb answered 503 to "
        "the audit reads)."
    )


async def test_a_tool_error_over_an_unreadable_answer_is_a_refusal() -> None:
    said = await _judged(
        _caused("the gene record is unreadable", DataParsingError("unreadable"))
    )

    assert said.startswith(
        "The site refused audit_gene_length (the gene record is unreadable)."
    )


async def test_a_genome_store_sign_in_refusal_reaches_the_turn() -> None:
    error = _caused("forbidden", JBrowseError("GET", "https://example.org/seq", 401))
    capability = SiteReadFailures[Any](reads=frozenset({_TOOL}))

    with pytest.raises(ToolError):
        await capability.on_tool_execute_error(
            MagicMock(),
            call=ToolCallPart(tool_name=_TOOL, args={}, tool_call_id="tc"),
            tool_def=ToolDefinition(name=_TOOL, parameters_json_schema={}),
            args={},
            error=error,
        )


_OUTAGE = "audit_gene_length got no answer from the site (the library said)."
_REFUSAL = "The site refused audit_gene_length (the library said)."


def _answered(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.org/service")
    return httpx.HTTPStatusError(
        f"answered {status}",
        request=request,
        response=httpx.Response(status, request=request),
    )


@pytest.mark.parametrize(
    ("cause", "opening"),
    [
        (TrackReadError("bigwig header unreadable"), _REFUSAL),
        (TimeoutError(), _OUTAGE),
        (TrackReadError("no such track", status=404), _REFUSAL),
        (GenomeIndexError("no contig"), _REFUSAL),
        (ValidationError(detail="bad"), _REFUSAL),
        (_answered(503), _OUTAGE),
        (_answered(404), _REFUSAL),
        (httpx.DecodingError("not gzip"), _REFUSAL),
        (WDKError("upstream failed", status=504), _OUTAGE),
        (JBrowseError("GET", "https://example.org/seq", 404), _REFUSAL),
    ],
)
async def test_a_tool_errors_cause_is_judged_by_its_status(
    cause: BaseException, opening: str
) -> None:
    said = await _judged(_caused("the library said", cause))

    assert said.startswith(opening)


@pytest.mark.parametrize(
    "cause",
    [
        WDKError("login required", status=403),
        TrackReadError("forbidden", status=401),
        _answered(401),
    ],
)
async def test_a_sign_in_refusal_inside_a_tool_error_reaches_the_turn(
    cause: BaseException,
) -> None:
    capability = SiteReadFailures[Any](reads=frozenset({_TOOL}))

    with pytest.raises(ToolError):
        await capability.on_tool_execute_error(
            MagicMock(),
            call=ToolCallPart(tool_name=_TOOL, args={}, tool_call_id="tc"),
            tool_def=ToolDefinition(name=_TOOL, parameters_json_schema={}),
            args={},
            error=_caused("the library said", cause),
        )
