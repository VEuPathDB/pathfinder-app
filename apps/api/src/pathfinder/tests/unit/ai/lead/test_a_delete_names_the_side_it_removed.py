"""An approved delete of one side of a withdrawn combination shows that side
retired, and never the side a remaining step answers."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.turn_facts import RetiredFact
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_BOTH = Constraint(
    kind=ConstraintKind.COMBINATION,
    requested_value="protein kinase domain AND no transmembrane domain",
    label="protein kinase domain AND no transmembrane domain",
    source=ConstraintSource.USER_EXPLICIT,
)
_SPEC = OperationalSpec(
    goal="kinases with no transmembrane domain",
    criteria=[
        Criterion(
            id="step_kinase",
            text="Giardia Assemblage B isolate GS_B genes with a protein kinase domain",
            search_name="GenesByInterproDomain",
        ),
        Criterion(
            id="step_no_tm",
            text="Giardia Assemblage B isolate GS_B genes without a transmembrane domain",
            search_name="GenesByTransmembraneDomains",
        ),
    ],
)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


async def test_the_retired_row_names_the_side_the_deleted_step_answered(
    stub_api: StubAPI,
) -> None:
    ctx = lead_run_context(
        user_prompt="Please remove the transmembrane domain exclusion.",
        strategy_session=session_with(
            combine("step_both", leaf("step_kinase"), leaf("step_no_tm")), {}
        ),
        tool_call_id="call_delete",
    )
    domain = ctx.deps.state.domain
    domain.operational_spec = _SPEC.model_copy(deep=True)
    domain.requirements = [_BOTH]
    domain.withdraw([_BOTH])
    before = turn_facts(ctx.deps).retired

    await delete_step(ctx, step_id="step_no_tm", reply="I remove that step.")

    assert (before, turn_facts(ctx.deps).retired) == (
        [],
        [RetiredFact(requirement="no transmembrane domain", state="withdrawn")],
    )
