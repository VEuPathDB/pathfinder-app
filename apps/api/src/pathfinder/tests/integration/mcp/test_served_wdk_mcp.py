"""veupathdb-wdk-mcp over its served endpoint, read by a real MCP client.

Every case skips unless the deployment serves the endpoint and the environment
names the credential the case needs. Resources a case creates are deleted.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
import veupathdb_mcp
from mcp.types import Tool
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelRetry
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.wdk_models import WDKAnswer
from veupathdb_mcp.controls.control_types import ControlTestResult
from veupathdb_mcp.server import MAX_CALL_SECONDS_META_KEY, TOOLS
from veupathdb_mcp.wdk.enrichment.gene_ids import GeneIdEnrichment
from veupathdb_mcp.wdk.helpers import extract_record_ids
from veupathdb_mcp.wdk.step_size import StepCountResult

from pathfinder.tests.integration.mcp._served import (
    ORGANISM,
    RECORD_TYPE,
    SITE,
    TARGET_PARAMETERS,
    TARGET_SEARCH,
    OwnedStep,
    connect,
    served_url,
    strategy_ids,
    wire,
)

pytestmark = pytest.mark.live_wdk

# A Toxoplasma gene, which a Plasmodium falciparum search cannot return.
NEGATIVE_CONTROL = "TGME49_205250"

CONTROL_GENE_COUNT = 3

# The identity of every enrichment column, which belongs to the analysis plugin
# and not to WDK: a wrong name yields an empty column and not an error.
PINNED_COLUMNS = {
    "go_function": ("goId", "goTerm"),
    "go_component": ("goId", "goTerm"),
    "go_process": ("goId", "goTerm"),
    "pathway": ("pathwayId", "pathwayName"),
    "word": ("word", "pathwayName"),
}


class ForeignStep(BaseModel):
    """A step of another VEuPathDB user, and the size its owner publishes."""

    step_id: int
    result_count: int


async def _list_tools(bearer: str) -> dict[str, Tool]:
    async with connect(bearer) as toolset:
        return {tool.name: tool for tool in await toolset.list_tools()}


def _declared_budget(tools: dict[str, Tool], name: str) -> float:
    """The call budget the served tool declares, which its client honours."""
    meta = tools[name].meta
    assert meta is not None, name
    return float(meta[MAX_CALL_SECONDS_META_KEY])


@pytest.fixture
async def foreign_step(user_bearer: str) -> ForeignStep:
    """A step another account owns, taken from the site's public strategies.

    The listing publishes the step's result count, so a refusal that carries
    that count is a leak and not a refusal.
    """
    reset = veupathdb_auth_token_ctx.set(user_bearer)
    try:
        api = get_strategy_api(SITE)
        own = await strategy_ids(api)
        published = [
            summary
            for summary in await api.list_public_strategies()
            if summary.strategy_id not in own and summary.estimated_size
        ]
    finally:
        veupathdb_auth_token_ctx.reset(reset)
    if not published:
        pytest.skip(f"{SITE} publishes no strategy of another account")
    owned_by_another = published[0]
    return ForeignStep(
        step_id=owned_by_another.root_step_id,
        result_count=owned_by_another.estimated_size or 0,
    )


async def test_the_endpoint_serves_the_inventory_this_tree_declares(
    service_bearer: str,
) -> None:
    """A container running older code answers with a different declaration."""
    served = await _list_tools(service_bearer)

    declared = {row.fn.__name__: row for row in TOOLS}
    assert sorted(served) == sorted(declared)
    for name, row in declared.items():
        annotations = served[name].annotations
        assert annotations is not None, name
        assert annotations.model_dump(exclude_none=True) == row.annotations.model_dump(
            exclude_none=True
        ), name
        assert served[name].outputSchema is not None, name
        for key, value in (row.meta or {}).items():
            assert (served[name].meta or {})[key] == value, name


async def test_the_server_declares_the_deployments_version(
    service_bearer: str,
) -> None:
    """serverInfo names this deployment, not the serving framework."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "version-pin", "version": "0"},
        },
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            served_url(),
            headers={
                "Authorization": f"Bearer {service_bearer}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json=payload,
        )
    response.raise_for_status()
    body = response.text
    data_lines = [line[5:] for line in body.splitlines() if line.startswith("data:")]
    document = json.loads(data_lines[0] if data_lines else body)
    server_info = document["result"]["serverInfo"]
    assert server_info["name"] == "veupathdb-wdk-mcp"
    assert server_info["version"] == veupathdb_mcp.__version__


async def test_the_inventory_is_the_same_across_two_connections(
    service_bearer: str,
) -> None:
    """Family 6: a client that reconnects reads the same tools."""
    first = await _list_tools(service_bearer)
    second = await _list_tools(service_bearer)

    assert {name: tool.model_dump(mode="json") for name, tool in first.items()} == {
        name: tool.model_dump(mode="json") for name, tool in second.items()
    }


async def test_a_catalog_read_needs_no_user_token(service_bearer: str) -> None:
    """The catalog is user-independent, so an application credential reads it."""
    async with connect(service_bearer) as toolset:
        record_types = await toolset.direct_call_tool(
            "list_record_types", {"site_id": SITE}
        )

    assert RECORD_TYPE in {entry["name"] for entry in record_types}


async def test_an_application_credential_cannot_read_a_step(
    service_bearer: str, owned_step: OwnedStep
) -> None:
    """The step a user token reads, an application credential is refused."""
    async with connect(service_bearer) as toolset:
        with pytest.raises(ModelRetry) as refusal:
            await toolset.direct_call_tool(
                "get_step_estimated_size",
                {"site_id": SITE, "wdk_step_id": owned_step.step_id},
            )

    assert "login" in str(refusal.value).lower()


async def test_an_unknown_site_is_refused_by_name(service_bearer: str) -> None:
    """Family 4: a refusal names the field the caller must correct."""
    async with connect(service_bearer) as toolset:
        with pytest.raises(ModelRetry) as refusal:
            await toolset.direct_call_tool("list_record_types", {"site_id": "nosuchdb"})

    message = str(refusal.value)
    assert "site_id" in message
    assert "nosuchdb" in message


async def test_a_user_token_reads_its_own_step(
    user_bearer: str, owned_step: OwnedStep
) -> None:
    async with connect(user_bearer) as toolset:
        payload = await toolset.direct_call_tool(
            "get_step_estimated_size",
            {
                "site_id": SITE,
                "wdk_step_id": owned_step.step_id,
                "wdk_strategy_id": owned_step.strategy_id,
            },
        )

    count = StepCountResult(**payload)
    assert count.step_id == owned_step.step_id
    assert count.count > 0


async def test_a_user_token_is_refused_the_step_of_another_user(
    user_bearer: str, foreign_step: ForeignStep
) -> None:
    """Family 2: one account's token reads nothing of another account's step."""
    async with connect(user_bearer) as toolset:
        with pytest.raises(ModelRetry) as refusal:
            await toolset.direct_call_tool(
                "get_step_estimated_size",
                {"site_id": SITE, "wdk_step_id": foreign_step.step_id},
            )

    message = str(refusal.value)
    assert str(foreign_step.step_id) in message
    assert str(foreign_step.result_count) not in re.findall(r"\d+", message)


async def test_a_step_sample_carries_records_the_caller_can_use(
    user_bearer: str, owned_step: OwnedStep
) -> None:
    async with connect(user_bearer) as toolset:
        payload = await toolset.direct_call_tool(
            "get_step_sample_records",
            {
                "site_id": SITE,
                "wdk_step_id": owned_step.step_id,
                "record_type": RECORD_TYPE,
                "limit": CONTROL_GENE_COUNT,
            },
        )

    answer = WDKAnswer.model_validate(payload)
    assert len(answer.records) == CONTROL_GENE_COUNT
    assert len(extract_record_ids(answer.records)) == CONTROL_GENE_COUNT


async def test_control_tests_run_end_to_end_and_leave_no_strategy(
    user_bearer: str, owned_step: OwnedStep
) -> None:
    """The one writer: it answers about the target and takes its strategy away."""
    api = get_strategy_api(SITE)
    async with connect(user_bearer) as toolset:
        sample = WDKAnswer.model_validate(
            await toolset.direct_call_tool(
                "get_step_sample_records",
                {
                    "site_id": SITE,
                    "wdk_step_id": owned_step.step_id,
                    "record_type": RECORD_TYPE,
                    "limit": CONTROL_GENE_COUNT,
                },
            )
        )
        positives = extract_record_ids(sample.records)
        tools = await toolset.list_tools()

        before = await strategy_ids(api)
        async with connect(
            user_bearer,
            read_seconds=_declared_budget(
                {tool.name: tool for tool in tools}, "run_control_tests_on_search"
            ),
        ) as writer:
            payload = await writer.direct_call_tool(
                "run_control_tests_on_search",
                {
                    "site_id": SITE,
                    "target_search_name": TARGET_SEARCH,
                    "target_parameters": wire(TARGET_PARAMETERS),
                    "positive_controls": positives,
                    "negative_controls": [NEGATIVE_CONTROL],
                    "record_type": RECORD_TYPE,
                },
            )
        after = await strategy_ids(api)

    result = ControlTestResult.model_validate(payload)
    assert result.positive is not None
    assert result.negative is not None
    assert result.positive.recall == 1.0
    assert result.negative.false_positive_rate == 0.0
    assert result.target.estimated_size is not None
    assert result.target.estimated_size > 0
    assert after - before == set()


async def test_enrichment_by_value_answers_within_its_declared_budget(
    user_bearer: str, owned_step: OwnedStep
) -> None:
    """The longest call the inventory declares, over the same transport."""
    async with connect(user_bearer) as toolset:
        sample = WDKAnswer.model_validate(
            await toolset.direct_call_tool(
                "get_step_sample_records",
                {
                    "site_id": SITE,
                    "wdk_step_id": owned_step.step_id,
                    "record_type": RECORD_TYPE,
                    "limit": CONTROL_GENE_COUNT,
                },
            )
        )
        genes = extract_record_ids(sample.records)
        tools = {tool.name: tool for tool in await toolset.list_tools()}

    async with connect(
        user_bearer, read_seconds=_declared_budget(tools, "enrich_gene_ids")
    ) as enricher:
        payload = await enricher.direct_call_tool(
            "enrich_gene_ids",
            {
                "site_id": SITE,
                "gene_ids": genes,
                "background": {"organism": ORGANISM},
            },
        )

    enrichment = GeneIdEnrichment.model_validate(payload)
    assert enrichment.gene_count == len(genes)
    assert {analysis.analysis_type for analysis in enrichment.analyses} == set(
        PINNED_COLUMNS
    )
    served_columns = {
        analysis.analysis_type: (
            analysis.source_columns.envelope,
            analysis.source_columns.term_id,
            analysis.source_columns.term_name,
        )
        for analysis in enrichment.analyses
    }

    assert served_columns == {
        analysis_type: ("resultData", term_id, term_name)
        for analysis_type, (term_id, term_name) in PINNED_COLUMNS.items()
    }
