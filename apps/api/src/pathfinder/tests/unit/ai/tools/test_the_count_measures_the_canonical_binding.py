"""``set_criterion`` counts the binding WDK will run.

A tree parameter scores its leaves alone, so a branch term selects the organisms
under it and matches nothing until the validation expands it.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, to_wire
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    bind,
    genes_by_text,
    serve_search,
)

# The branch the request names, and the one organism under it.
_BRANCH = "Plasmodium"
_LEAF = "Plasmodium falciparum 3D7"


def _expand_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation answers the leaves, the way the canonicalizer does."""

    async def _validate(
        _search: object,
        *,
        parameters: Mapping[str, ParamValue],
        callbacks: object,
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(
            params=dict(parameters)
            | {"text_search_organism": MultiPickValue(values=[_LEAF])}
        )

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)


def _record_the_count(
    monkeypatch: pytest.MonkeyPatch, count: int | None
) -> list[dict[str, ParamValue]]:
    """Answer one fixed count, and keep the parameters it was asked about."""
    asked: list[dict[str, ParamValue]] = []

    async def _count(
        _site_id: str,
        _record_type: str,
        _search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        asked.append(dict(params))
        return count

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    return asked


@pytest.mark.asyncio
async def test_the_count_reads_the_values_the_validation_canonicalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _expand_the_branch(monkeypatch)
    asked = _record_the_count(monkeypatch, 1375)

    result = await bind(AgentToolState(), "GenesByText", KINASE_PARAMS)

    assert len(asked) == 1
    assert to_wire(asked[0]["text_search_organism"]) == f'["{_LEAF}"]'
    assert to_wire(asked[0]["text_expression"]) == "kinase"
    assert result.result_count == 1375


@pytest.mark.asyncio
async def test_the_criterion_keeps_the_term_the_request_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    _expand_the_branch(monkeypatch)
    _record_the_count(monkeypatch, 1375)
    state = AgentToolState()

    result = await bind(state, "GenesByText", KINASE_PARAMS)

    stored = state.operational_spec_draft.criteria[0].resolved_params
    assert to_wire(stored["text_search_organism"]) == f'["{_BRANCH}"]'
    assert result.resolved_params["text_search_organism"] == f'["{_BRANCH}"]'


@pytest.mark.asyncio
async def test_a_binding_with_no_branch_to_expand_counts_what_it_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation that changes nothing leaves the count on the recorded values."""
    serve_search(monkeypatch, genes_by_text)
    asked = _record_the_count(monkeypatch, 3)
    state = AgentToolState()

    await bind(state, "GenesByText", KINASE_PARAMS)

    assert asked[0] == state.operational_spec_draft.criteria[0].resolved_params
