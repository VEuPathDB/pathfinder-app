"""What the stated-value guard asks the catalog for one written tree."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb_mcp.catalog import ValidatedParams, ValidationCallbacks

from pathfinder.domain.strategy.spec_edit_guard import StatedCriterion
from pathfinder.services.strategies import stated_sides
from pathfinder.services.strategies.stated_sides import canonicalize_stated_leaves

_STATED = "step_780fd940"
_EMPTY = "step_fb1f017c"


def _stated() -> dict[str, StatedCriterion]:
    values: dict[str, ParamValue] = {
        "ProfileGeneId": StringValue(value="TGME49_201780")
    }
    return {
        _STATED: StatedCriterion(text="similar to MIC2", values=values),
        _EMPTY: StatedCriterion(text="similar to RON2", values=dict(values)),
    }


def _tree() -> StrategyStepNode:
    """A stated leaf that carries a value, beside a stated leaf that carries none."""
    return StrategyStepNode(
        id="step_7eca55ff",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id=_STATED,
            search_name="GenesByToxoProfileSimilarity",
            parameters={"ProfileGeneId": StringValue(value="TGME49_201780")},
        ),
        secondary_input=StrategyStepNode(
            id=_EMPTY, search_name="GenesByToxoProfileSimilarity"
        ),
    )


def _callbacks() -> ValidationCallbacks:
    async def _record_type(record_type: str | None, search_name: str | None) -> str:
        del search_name
        return record_type or "transcript"

    async def _hint(search_name: str, record_type: str | None) -> str | None:
        del search_name, record_type
        return None

    return ValidationCallbacks(
        resolve_record_type_for_search=_record_type, find_record_type_hint=_hint
    )


async def test_a_stated_leaf_that_carries_no_value_asks_the_catalog_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, ParamValue]] = []

    async def _record(*_args: Any, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
        seen.append(params)
        return ValidatedParams(params=params, record_class="transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", _record)

    writes = await canonicalize_stated_leaves(
        root=_tree(),
        stated=_stated(),
        site_id="toxodb",
        record_type="transcript",
        callbacks=_callbacks(),
    )

    assert [write.step_id for write in writes] == [_STATED]
    assert len(seen) == 1
