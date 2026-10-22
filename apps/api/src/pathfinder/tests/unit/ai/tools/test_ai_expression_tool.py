"""The agent tool over the aiExpression reporter, driven by recorded responses.

Only the transport is replaced: the client, its models, the service and the
tool all run, so the fixture proves the whole path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
import respx
from pydantic import JsonValue, TypeAdapter
from veupathdb.errors import WDKError
from veupathdb.wdk import AI_EXPRESSION_REPORT_PATH, AiExpressionStatus, get_site
from veupathdb_mcp import ToolErrorPayload
from veupathdb_mcp.wdk import NO_SUMMARY_ON_THE_SITE, GeneExpressionSummary

from pathfinder.ai.tools.standalone import gene
from pathfinder.tests._support.qa_recording import client_recording
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

REFUSAL = "No Gene record found for the primary key values"

SITE = "plasmodb"
SUMMARIZED_GENE = "PF3D7_0709000"
INCOMPLETE_GENE = "PF3D7_1133400"
_BODY: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
_GENE_RECORD_TYPE = {
    "urlSegment": "gene",
    "primaryKeyColumnRefs": ["source_id", "project_id"],
}


@contextmanager
def _served(body: JsonValue) -> Iterator[respx.Route]:
    site = get_site(SITE)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(f"{site.web_base_url}/app").mock(return_value=httpx.Response(200))
        router.get(f"{site.service_url}/record-types/gene").mock(
            return_value=httpx.Response(200, json=_GENE_RECORD_TYPE)
        )
        yield router.post(f"{site.service_url}{AI_EXPRESSION_REPORT_PATH}").mock(
            return_value=httpx.Response(200, json=body)
        )


def _sent(report: respx.Route) -> dict[str, JsonValue]:
    return _BODY.validate_json(report.calls.last.request.content)


async def test_a_gene_with_experiments_outstanding_reaches_the_agent_as_a_miss() -> (
    None
):
    body = client_recording("ai_expression_experiments_incomplete").json_body()
    ctx = agent_run_context()

    with _served(body) as report:
        returned = await gene.get_ai_expression_summary(ctx, INCOMPLETE_GENE)

    assert report.call_count == 1
    assert _sent(report)["reportConfig"] == {"populateIfNotPresent": False}
    assert _sent(report)["searchConfig"] == {
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


async def test_a_summarized_gene_reaches_the_agent_without_experiment_counts() -> None:
    """The site sends no count beside a summary, so the tool reports none."""
    body = client_recording("ai_expression_summary_present").json_body()
    ctx = agent_run_context()

    with _served(body):
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


async def test_a_summary_built_on_part_of_the_data_says_so() -> None:
    """The site states what its summary covers, so the line the user reads says it."""
    body = client_recording("ai_expression_summary_present").json_body()
    assert isinstance(body, dict)
    entry = body[SUMMARIZED_GENE]
    assert isinstance(entry, dict)
    entry["basedOnIncompleteData"] = True
    ctx = agent_run_context()

    with _served(body):
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
    ctx = agent_run_context()

    returned = await gene.get_ai_expression_summary(ctx, "NOT_A_GENE")

    result = returned.return_value
    assert isinstance(result, ToolErrorPayload)
    assert result.ok is False
    assert result.code == "WDK_ERROR"
    assert result.message == f"VEuPathDB service error: {REFUSAL}"
    assert summary_of(returned).data["status"] == "warn"
