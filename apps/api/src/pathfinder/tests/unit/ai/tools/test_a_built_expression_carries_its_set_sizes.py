"""build_phyletic_expression answers each set's genome count from the site's
taxonomy, and refuses a genome count larger than its set before it writes."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import PhyleticTree
from veupathdb_mcp.catalog import PhyleticExpressionResult, PhyleticPattern

from pathfinder.ai.tools.standalone import orthomcl_expressions
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    BuiltExpression,
    build_phyletic_expression,
)
from pathfinder.domain.strategy.pattern_sets import SetSize
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_SITE = "orthomcl"


class _Writes:
    def __init__(self) -> None:
        self.patterns: list[PhyleticPattern] = []


@pytest.fixture
def writes(monkeypatch: pytest.MonkeyPatch) -> _Writes:
    held = _Writes()

    async def _tree(site_id: str) -> PhyleticTree | None:
        return synthetic_tree()

    async def _write(
        site_id: str, written: PhyleticPattern
    ) -> PhyleticExpressionResult:
        held.patterns.append(written)
        return PhyleticExpressionResult(
            site_id=site_id,
            expression="FERN>=2T",
            reading="at least 2 of the genomes of FERN",
            groups=17,
            codes=("FERN",),
            maximum_reads=0,
        )

    monkeypatch.setattr(orthomcl_expressions, "ortho_taxonomy", _tree)
    monkeypatch.setattr(orthomcl_expressions, "write_phyletic_expression", _write)
    return held


def _count(codes: list[str], value: int) -> PhyleticPattern:
    return pattern(
        {
            "kind": "count",
            "of": {"kind": "codes", "codes": codes},
            "measure": "genomes",
            "condition": "at_least",
            "value": value,
        }
    )


async def test_the_result_carries_the_genomes_of_each_set(writes: _Writes) -> None:
    result = await build_phyletic_expression(
        agent_run_context(site_id=_SITE), _count(["FERN"], 2)
    )

    built = returned(result, BuiltExpression)
    assert built.sets == (SetSize(kind="codes", codes=("FERN",), genomes=3),)
    assert len(writes.patterns) == 1


async def test_a_count_larger_than_its_set_is_refused_before_it_is_written(
    writes: _Writes,
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await build_phyletic_expression(
            agent_run_context(site_id=_SITE), _count(["MOSS"], 4)
        )

    assert str(refused.value) == (
        "at least 4 genomes of MOSS asks for more genomes than it holds: its codes "
        "cover 2 genomes on the site's taxonomy. Read each set's genome count from "
        "`sets`, or state the bound as a share."
    )
    assert writes.patterns == []
