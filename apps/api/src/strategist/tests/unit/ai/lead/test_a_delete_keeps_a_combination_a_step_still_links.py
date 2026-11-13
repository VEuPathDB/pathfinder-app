from __future__ import annotations

import pytest

from strategist.ai.lead.lead_tools import delete_step
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_BOTH = Constraint(
    id="r_both",
    kind=ConstraintKind.COMBINATION,
    requested_value="protein kinase domain AND no transmembrane domain",
    label="protein kinase domain AND no transmembrane domain",
    source=ConstraintSource.USER_EXPLICIT,
)
_SPEC = OperationalSpec(
    goal="kinases with no transmembrane domain",
    criteria=[
        Criterion(
            id=cid,
            text=text,
            search_name=search,
            answers=[RequirementLink(requirement=_BOTH.id)],
        )
        for cid, text, search in (
            (
                "step_kinase",
                "Giardia Assemblage B isolate GS_B genes with a protein kinase domain",
                "GenesByInterproDomain",
            ),
            (
                "step_no_tm",
                "Giardia Assemblage B isolate GS_B genes without a transmembrane domain",
                "GenesByTransmembraneDomains",
            ),
        )
    ],
)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


async def test_a_delete_of_one_linked_step_keeps_the_combination_live(
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

    await delete_step(ctx, step_id="step_no_tm", reply="I remove that step.")

    assert (domain.requirements, turn_facts(ctx.deps).retired) == ([_BOTH], [])
