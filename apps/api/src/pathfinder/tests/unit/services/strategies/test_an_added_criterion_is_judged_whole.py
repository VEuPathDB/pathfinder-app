"""The binding the stated-value guard asks the catalog to judge."""

from __future__ import annotations

from typing import Any, NamedTuple

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import StepKind, StrategyStep, StrategyStepNode
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import StatedCriterion
from pathfinder.services.strategies import stated_sides
from pathfinder.services.strategies.stated_sides import canonical_batch

_SEARCH = "GenesByInterproDomain"
_STEP = "step_domain"


class _Read(NamedTuple):
    """One catalog read, with the parameters the caller asked it to judge."""

    search_name: str
    parameters: dict[str, ParamValue]


def _record_reads(monkeypatch: pytest.MonkeyPatch) -> list[_Read]:
    """Answer every catalog read with the values it was given, and keep them."""
    reads: list[_Read] = []

    async def _echo(ctx: SearchContext, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs["parameters"])
        reads.append(_Read(search_name=ctx.search_name, parameters=params))
        return ValidatedParams(params=params, record_class="transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", _echo)
    return reads


def _binding(*, accession: str, domain: str) -> dict[str, ParamValue]:
    return {
        "organism": MultiPickValue(values=["Anopheles gambiae PEST"]),
        "domain_database": SinglePickValue(value="Pfam"),
        "domain_accession": StringValue(value=accession),
        "domain_typeahead": MultiPickValue(values=[domain]),
    }


def _graph() -> StrategyGraph:
    graph = StrategyGraph("graph_1", "Domain screen", "vectorbase")
    graph.record_type = "transcript"
    return graph


def _states(domain: str) -> dict[str, ParamValue]:
    """The subset of the binding the criterion's own words carry."""
    return {
        "domain_database": SinglePickValue(value="Pfam"),
        "domain_typeahead": MultiPickValue(values=[domain]),
    }


async def test_a_leaf_the_batch_adds_is_judged_on_its_whole_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An added leaf's stated values are read under every value it carries."""
    reads = _record_reads(monkeypatch)
    stated = {
        _STEP: StatedCriterion(text="Pfam domain PF03392", values=_states("PF03392"))
    }
    op = AddLeafOp(
        step=StrategyStepNode(
            id=_STEP,
            search_name=_SEARCH,
            parameters=_binding(accession="N/A", domain="PF03392"),
        ),
        attach=AttachNewRoot(),
    )

    batch = await canonical_batch(
        graph=_graph(), stated=stated, site_id="vectorbase", ops=[op]
    )

    assert [read.search_name for read in reads] == [_SEARCH, _SEARCH]
    assert reads[1].parameters == _binding(accession="N/A", domain="PF03392")
    assert batch.sides.stated[_STEP].values == _states("PF03392")
    assert batch.sides.entry[_STEP] == {}


async def test_a_step_the_batch_updates_is_judged_on_the_values_it_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An updated step's stated values are read under the step's own binding."""
    reads = _record_reads(monkeypatch)
    graph = _graph()
    graph.steps[_STEP] = StrategyStep(
        id=_STEP,
        kind=StepKind.SEARCH,
        search_name=_SEARCH,
        parameters=_binding(accession="N/A", domain="PF00001"),
    )
    graph.recompute_roots()
    stated = {
        _STEP: StatedCriterion(text="Pfam domain PF03392", values=_states("PF03392"))
    }
    op = UpdateStepParamsOp(step_id=_STEP, parameters=_states("PF03392"))

    batch = await canonical_batch(
        graph=graph, stated=stated, site_id="vectorbase", ops=[op]
    )

    assert [read.search_name for read in reads] == [_SEARCH, _SEARCH, _SEARCH]
    assert reads[1].parameters == _binding(accession="N/A", domain="PF03392")
    assert reads[2].parameters == _binding(accession="N/A", domain="PF00001")
    assert batch.sides.entry[_STEP] == _states("PF00001")
