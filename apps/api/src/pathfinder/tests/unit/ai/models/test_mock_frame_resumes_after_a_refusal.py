"""After any refusal, or a history the run compacted, the FRAME goes on from its
next unmade call: a criterion its workspace holds is never bound again."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_workspace
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionReply, criterion_call, frame_call
from pathfinder.ai.models.mock.strategy_specs import intersect_spec
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

SITES = ("plasmodb", "vectorbase")
_READ = frozenset({"search_for_searches", "list_searches"})


def _workspace(site_id: str, *criterion_ids: str) -> str:
    """The FRAME workspace pinned with these criteria bound."""
    organism = MultiPickValue(values=[SiteValues.for_site(site_id).organism])
    state = AgentToolState()
    for cid in criterion_ids:
        state.frame_set_criterion(
            Criterion(
                id=cid,
                text=f"{cid} genes",
                search_name="GenesWithSignalPeptide",
                resolved_params={"organism": organism},
            )
        )
    return pinned_frame_workspace(agent_run_context(agent_state=state)) or ""


@pytest.mark.parametrize("site_id", SITES)
def test_a_criterion_the_workspace_holds_is_not_bound_again(site_id: str) -> None:
    spec = intersect_spec(SiteValues.for_site(site_id))
    signal, domains = spec.criteria
    pinned = _workspace(site_id, signal.criterion_id)

    call = frame_call(spec, _READ, [], pinned)

    assert (call.tool_name, call.args_as_dict()["criterion_id"]) == (
        "set_criterion",
        domains.criterion_id,
    )
    assert criterion_call(signal, [], pinned) is None


@pytest.mark.parametrize("site_id", SITES)
def test_a_refused_proposal_is_proposed_again_and_no_other(site_id: str) -> None:
    spec = intersect_spec(SiteValues.for_site(site_id))
    signal, domains = spec.criteria
    pinned = _workspace(site_id, signal.criterion_id)
    opened = CriterionReply(
        criterion_id=domains.criterion_id,
        search_name=domains.search_name,
        params_template={"organism": None, "min_tm": None, "max_tm": None},
    )

    call = frame_call(spec, _READ, [opened], pinned)

    assert call.args_as_dict()["criterion_id"] == domains.criterion_id
    assert call.args_as_dict()["params"]["min_tm"] == "2"


@pytest.mark.parametrize("site_id", SITES)
def test_nothing_is_bound_once_the_structure_is_set(site_id: str) -> None:
    spec = intersect_spec(SiteValues.for_site(site_id))
    pinned = _workspace(site_id, *(c.criterion_id for c in spec.criteria))

    call = frame_call(spec, _READ | {"set_structure"}, [], pinned)

    assert call.tool_name == "final_result"
