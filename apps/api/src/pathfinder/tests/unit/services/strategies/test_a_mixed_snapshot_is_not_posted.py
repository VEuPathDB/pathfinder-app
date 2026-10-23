from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.services.strategies.materialize import materialize_strategy_snapshot
from pathfinder.tests._support.mixed_record_classes import (
    MIXED_REFUSAL,
    mixed_snapshot,
)
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api


async def test_a_snapshot_that_joins_two_record_types_keeps_the_plan_and_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = install_stub_api(monkeypatch)
    serve_orthomcl_record_classes(monkeypatch)

    result = await materialize_strategy_snapshot(
        site_id="orthomcl",
        conversation_id=uuid4(),
        name="Trypanothione reductase",
        strategy_ast=mixed_snapshot(),
    )

    assert (api.calls, result.wdk_strategy_id, result.step_count) == ([], None, 3)
    assert "wdkStepIds" not in result.strategy_ast
    assert result.strategy_ast["wdkPushErrors"] == {"step_join": MIXED_REFUSAL}
