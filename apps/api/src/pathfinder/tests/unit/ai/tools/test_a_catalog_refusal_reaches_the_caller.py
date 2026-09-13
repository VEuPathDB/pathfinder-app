"""A value the catalog turns down is answered, on every path that writes one.

The commit puts a written value in the catalog's form, so its refusal reaches
callers that used to see the value only at push time.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.strategies import stated_sides
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._eda_step_doubles import bound, read_detail

from ._strategy_edit_stubs import StubAPI, ctx, install_stub_api, leaf, seed

_TURNED_DOWN = "Parameter 'organism' does not accept 'NotARealOrganism'."


def _refusal() -> ValidationError:
    return ValidationError(
        title="Invalid parameter value",
        detail=_TURNED_DOWN,
        errors=[
            {
                "param": "organism",
                "value": "NotARealOrganism",
                "validOptions": ["Pf3D7", "PvP01"],
            }
        ],
    )


async def _turns_the_value_down(*_args: Any, **_kwargs: Any) -> ValidatedParams:
    raise _refusal()


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = install_stub_api(monkeypatch)
    monkeypatch.setattr(stated_sides, "validate_parameters", _turns_the_value_down)
    return api


@pytest.mark.usefixtures("stub_api")
async def test_apply_operations_answers_with_the_refusal() -> None:
    deps = seed(
        leaf("a", params={"organism": MultiPickValue(values=["Pf3D7"])}),
        wdk_step_ids={"a": 100},
    )
    graph = deps.strategy_session.graph
    assert graph is not None

    with pytest.raises(ModelRetry) as excinfo:
        await apply_operations(
            ctx(deps),
            strategy_revision(graph.to_strategy_ast()),
            [
                UpdateStepParamsOp(
                    step_id="a",
                    parameters={
                        "organism": MultiPickValue(values=["NotARealOrganism"])
                    },
                )
            ],
        )

    assert "NotARealOrganism" in str(excinfo.value)
    assert graph.steps["a"].parameters == {"organism": MultiPickValue(values=["Pf3D7"])}


async def test_create_eda_step_answers_with_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuse(**_kwargs: Any) -> None:
        raise _refusal()

    monkeypatch.setattr(eda_step, "bound_analysis", bound)
    monkeypatch.setattr(eda_step, "read_analysis", read_detail)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", _refuse)
    lead_ctx = lead_run_context(
        user_prompt="export the febrile subset",
        strategy_session=seed(leaf("a"), wdk_step_ids={"a": 100}).strategy_session,
    )

    with pytest.raises(ModelRetry) as excinfo:
        await eda_step.create_eda_step(lead_ctx)

    assert _TURNED_DOWN in str(excinfo.value)
