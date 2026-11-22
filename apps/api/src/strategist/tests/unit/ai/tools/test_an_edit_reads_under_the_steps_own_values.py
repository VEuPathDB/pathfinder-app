"""An edit that states one dependent value reads it under the values the step holds."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry, Tool
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import read_under_parents

from strategist.ai.tools.standalone import _stated_values, strategy_edits
from strategist.ai.tools.standalone.strategy import apply_operations
from strategist.ai.tools.standalone.strategy_edits import update_leaf_params
from strategist.domain.strategy.operations import GraphOperation
from strategist.services.strategies.commit import CommitResult
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.recorded_searches import client_search
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
    pin_apply,
    revision_of,
)

_PF = "Plasmodium falciparum 3D7"
_VIVAX = "Plasmodium vivax P01"
_SAMPLES = "variation_sample_meta"
_PERU: JsonValue = [
    {"field": "Dataset", "value": ["WGS of Patient Isolates from Peru"]}
]
_UNDER = {
    f'["{_PF}"]': client_search("search_genes_by_ngs_snps"),
    f'["{_VIVAX}"]': client_search("search_genes_by_ngs_snps_under_another_organism"),
}


@pytest.fixture(autouse=True)
def _reads(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _read(
        _site_id: str,
        _search_name: str,
        stated: Mapping[str, JsonValue] | None,
        *,
        record_type: str | None = None,
        bound: Mapping[str, ParamValue],
    ) -> dict[str, ParamValue]:
        del record_type

        async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
            organism = context.get("organismSinglePick", f'["{_PF}"]')
            return list(_UNDER[organism].parameters or [])

        return await read_under_parents(
            fetch_at, stated or {}, NoFilterReads(), bound=bound
        )

    monkeypatch.setattr(_stated_values, "read_stated_parameters", _read)


def _snps(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_s",
        search_name="GenesByNgsSnps",
        parameters={"organismSinglePick": MultiPickValue(values=[organism])},
    )


def _committed_edits(monkeypatch: pytest.MonkeyPatch) -> list[GraphOperation]:
    ops: list[GraphOperation] = []

    async def _commit(*, deps: object, op: GraphOperation) -> CommitResult:
        del deps
        ops.append(op)
        return CommitResult(description="applied")

    monkeypatch.setattr(strategy_edits, "apply_and_commit", _commit)
    return ops


async def test_a_vivax_step_takes_a_peru_isolate_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops = _committed_edits(monkeypatch)
    ctx, _ = context_and_commit(graph_with(_snps(_VIVAX)), [])

    await update_leaf_params(ctx, "step_s", {_SAMPLES: _PERU})

    [op] = ops
    assert op.model_dump()["parameters"].keys() == {_SAMPLES}


async def test_a_falciparum_step_refuses_a_peru_isolate_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops = _committed_edits(monkeypatch)
    ctx, _ = context_and_commit(graph_with(_snps(_PF)), [])

    with pytest.raises(ModelRetry, match="WGS of Patient Isolates from Peru"):
        await update_leaf_params(ctx, "step_s", {_SAMPLES: _PERU})

    assert ops == []


def _edit(parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"kind": "updateStepParams", "stepId": "step_s", "parameters": parameters}


async def _batch(
    monkeypatch: pytest.MonkeyPatch,
    organism: str,
    edits: list[JsonValue] | None = None,
) -> list[str]:
    graph = graph_with(_snps(organism))
    committed: list[list[GraphOperation]] = []
    ctx, commit = context_and_commit(graph, committed)
    pin_apply(monkeypatch, commit)
    args = Tool(apply_operations).function_schema.validator.validate_python(
        {
            "base_revision": revision_of(graph),
            "operations": edits or [_edit({_SAMPLES: _PERU})],
        }
    )
    await apply_operations(ctx, **args)
    return [op.kind for ops in committed for op in ops]


async def test_a_batch_edit_of_a_vivax_step_takes_a_peru_isolate_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _batch(monkeypatch, _VIVAX) == ["updateStepParams"]


async def test_a_batch_edit_of_a_falciparum_step_refuses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry, match="WGS of Patient Isolates from Peru"):
        await _batch(monkeypatch, _PF)


async def test_a_batch_reads_a_filter_under_the_organism_it_set_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edits: list[JsonValue] = [
        _edit({"organismSinglePick": [_VIVAX]}),
        _edit({_SAMPLES: _PERU}),
    ]

    assert await _batch(monkeypatch, _PF, edits) == [
        "updateStepParams",
        "updateStepParams",
    ]


async def test_a_batch_refuses_a_filter_set_before_its_organism_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edits: list[JsonValue] = [
        _edit({_SAMPLES: _PERU}),
        _edit({"organismSinglePick": [_VIVAX]}),
    ]

    with pytest.raises(ModelRetry, match="WGS of Patient Isolates from Peru"):
        await _batch(monkeypatch, _PF, edits)
