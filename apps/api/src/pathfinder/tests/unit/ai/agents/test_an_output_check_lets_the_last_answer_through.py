from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK, may_refuse


def _at(retry: int) -> RunContext[None]:
    return RunContext(
        deps=None, model=TestModel(), usage=RunUsage(), retry=retry, max_retries=3
    )


@pytest.mark.parametrize(
    ("retry", "used", "refuses"),
    [(0, 0, True), (1, 1, True), (2, REFUSALS_PER_CHECK, False), (3, 0, False)],
)
def test_a_check_refuses_within_its_bound_and_never_on_the_last_answer(
    retry: int, used: int, refuses: bool
) -> None:
    assert may_refuse(_at(retry), used) is refuses
