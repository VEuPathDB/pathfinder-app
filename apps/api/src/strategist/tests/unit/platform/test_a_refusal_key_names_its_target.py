from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb_mcp.records import TableRequest

from strategist.ai.graph.runtime import AgentDeps
from strategist.domain.refusal import RefusalKey
from strategist.platform.refusals import KeyedRefusalToolset
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.tests.unit.platform.test_a_refusal_is_counted_per_key import (
    _agent,
    _deps,
)
from strategist.tests.unit.platform.test_a_refusal_key_resets_and_persists import (
    _script,
)

_THREADS = (
    UUID("3f2b1c04-0d55-4a19-9c6a-7c1f5f2a8b31"),
    UUID("d6edd975-f6d9-482e-bc50-3d666b55227f"),
)


async def count_by_column(
    ctx: RunContext[AgentDeps], search: VariantInput, record_type: str, column: str
) -> str:
    del ctx, record_type
    msg = f"{search.search_name} has no column {column}."
    raise ModelRetry(msg)


async def read_my_thread(ctx: RunContext[AgentDeps], conversation_id: UUID) -> str:
    del ctx
    msg = f"{conversation_id} is not one of the researcher's threads."
    raise ModelRetry(msg)


async def read_search_table(
    ctx: RunContext[AgentDeps], request: TableRequest, site_id: str | None = None
) -> str:
    del ctx, site_id
    msg = f"{request.search_name} reads no table {request.table}."
    raise ModelRetry(msg)


async def _keys(tool: Any, name: str, calls: list[dict[str, Any]]) -> list[RefusalKey]:
    deps = _deps()
    await _agent(
        _script(name, calls), KeyedRefusalToolset(wrapped=FunctionToolset([tool]))
    ).run("refuse", deps=deps)
    return [use.key for use in deps.refusal_book.ledger.uses]


def _counted(search_name: str) -> dict[str, Any]:
    return {
        "search": {"label": "early", "searchName": search_name, "parameters": {}},
        "record_type": "transcript",
        "column": "organism",
    }


async def test_two_searches_counted_by_one_column_keep_two_keys() -> None:
    keys = await _keys(
        count_by_column,
        "count_by_column",
        [_counted("GenesByTaxon"), _counted("GenesByText")],
    )

    assert keys == [
        RefusalKey(
            check="count_by_column",
            criterion="early; record_type=transcript; column=organism",
            search=search,
        )
        for search in ("GenesByTaxon", "GenesByText")
    ]


async def test_two_threads_keep_two_keys() -> None:
    keys = await _keys(
        read_my_thread,
        "read_my_thread",
        [{"conversation_id": str(thread)} for thread in _THREADS],
    )

    assert keys == [
        RefusalKey(check="read_my_thread", criterion=f"conversation_id={thread}")
        for thread in _THREADS
    ]


async def test_a_nested_request_is_keyed_by_its_search() -> None:
    request = {
        "recordType": "organism",
        "searchName": "GenomeDataTypes",
        "table": "BUSCO",
    }

    keys = await _keys(read_search_table, "read_search_table", [{"request": request}])

    assert keys == [
        RefusalKey(
            check="read_search_table",
            criterion="record_type=organism",
            search="GenomeDataTypes",
        )
    ]
