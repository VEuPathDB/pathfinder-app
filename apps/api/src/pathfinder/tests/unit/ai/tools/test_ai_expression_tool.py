"""The agent tool over the aiExpression reporter, driven by recorded responses.

Only the transport is replaced: the client, its models, the service and the
tool all run, so the fixture proves the whole path.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import JsonValue
from veupathdb.errors import WDKError
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionStatus,
)
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb_mcp import ToolErrorPayload
from veupathdb_mcp.wdk import (
    NO_SUMMARY_ON_THE_SITE,
    GeneExpressionSummary,
    ai_expression,
)

from pathfinder.ai.tools.standalone import gene
from pathfinder.tests.unit.ai.tools.conftest import agent_state_ctx, summary_of

REFUSAL = "No Gene record found for the primary key values"

SUMMARIZED_GENE = "PF3D7_0709000"
INCOMPLETE_GENE = "PF3D7_1133400"


class _Transport:
    def __init__(self, body: JsonValue) -> None:
        self._body = body
        self.paths: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> JsonValue:
        self.paths.append(path)
        self.bodies.append(json or {})
        return self._body


def _serve(monkeypatch: pytest.MonkeyPatch, fixture: str) -> _Transport:
    """Answer the reporter with a recorded body, through the real client."""
    transport = _Transport(load_recorded(fixture).json_body())
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", transport)
    monkeypatch.setattr(ai_expression, "get_wdk_client", lambda _site: client)
    return transport


async def test_a_gene_with_experiments_outstanding_reaches_the_agent_as_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _serve(monkeypatch, "ai_expression_experiments_incomplete")
    ctx = agent_state_ctx()

    returned = await gene.get_ai_expression_summary(ctx, INCOMPLETE_GENE)

    assert transport.paths == [AI_EXPRESSION_REPORT_PATH]
    assert transport.bodies[0]["reportConfig"] == {"populateIfNotPresent": False}
    assert transport.bodies[0]["searchConfig"] == {
        "parameters": {"primaryKeys": f"{INCOMPLETE_GENE},PlasmoDB"}
    }
    result = returned.return_value
    assert isinstance(result, GeneExpressionSummary)
    assert result.site_id == "plasmodb"
    assert result.gene_id == INCOMPLETE_GENE
    assert result.summary is None
    assert result.unavailable_reason == NO_SUMMARY_ON_THE_SITE
    assert result.result_status is AiExpressionStatus.EXPERIMENTS_INCOMPLETE
    assert result.num_experiments == 41
    assert result.num_experiments_complete == 0
    assert summary_of(returned).data["status"] == "empty"


async def test_a_summarized_gene_reaches_the_agent_without_experiment_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The site sends no count beside a summary, so the tool reports none."""
    _serve(monkeypatch, "ai_expression_summary_present")
    ctx = agent_state_ctx()

    returned = await gene.get_ai_expression_summary(ctx, SUMMARIZED_GENE)

    result = returned.return_value
    assert isinstance(result, GeneExpressionSummary)
    assert result.result_status is AiExpressionStatus.PRESENT
    assert result.summary is not None
    assert result.unavailable_reason is None
    assert result.num_experiments is None
    assert result.num_experiments_complete is None
    assert result.based_on_incomplete_data is False
    assert summary_of(returned).data["status"] == "ok"
    line = summary_of(returned).data["summary"]
    assert isinstance(line, str)
    assert line.startswith(f"Expression summary for {SUMMARIZED_GENE}: ")
    assert "part of the experiment set" not in line


async def test_a_summary_built_on_part_of_the_data_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The site states what its summary covers, so the line the user reads says it."""
    body = load_recorded("ai_expression_summary_present").json_body()
    assert isinstance(body, dict)
    entry = body[SUMMARIZED_GENE]
    assert isinstance(entry, dict)
    entry["basedOnIncompleteData"] = True
    transport = _Transport(body)
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", transport)
    monkeypatch.setattr(ai_expression, "get_wdk_client", lambda _site: client)
    ctx = agent_state_ctx()

    returned = await gene.get_ai_expression_summary(ctx, SUMMARIZED_GENE)

    result = returned.return_value
    assert isinstance(result, GeneExpressionSummary)
    assert result.based_on_incomplete_data is True
    line = summary_of(returned).data["summary"]
    assert isinstance(line, str)
    assert line.startswith(
        f"Expression summary for {SUMMARIZED_GENE} (part of the experiment set): "
    )


async def test_a_refused_gene_reaches_the_agent_as_a_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuse(*_args: object, **_kwargs: object) -> GeneExpressionSummary:
        raise WDKError(REFUSAL, status=422)

    monkeypatch.setattr(gene, "get_gene_expression_summary", _refuse)
    ctx = agent_state_ctx()

    returned = await gene.get_ai_expression_summary(ctx, "NOT_A_GENE")

    result = returned.return_value
    assert isinstance(result, ToolErrorPayload)
    assert result.ok is False
    assert result.code == "WDK_ERROR"
    assert result.message == f"VEuPathDB service error: {REFUSAL}"
    assert summary_of(returned).data["status"] == "warn"
