"""The spec a framing pass hands the Lead states each bound copy as criteria of
its own, so the build and the edit read an ordinary tree."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.sub_agent_tools import apply_agent_state
from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.domain.strategy._orthology import round_trip_spec


def _kinds(node: StructureNode) -> set[str]:
    return {node.kind, *(kind for child in node.inputs for kind in _kinds(child))}


def test_the_lead_receives_the_copy_as_criteria() -> None:
    deps = lead_deps(pipeline_state(user_message_id=uuid4()))
    state = AgentToolState()
    state.operational_spec_draft = round_trip_spec()

    apply_agent_state(deps, agent_run_context(agent_state=state).deps)

    handed = deps.state.domain.operational_spec
    assert handed is not None
    assert handed.structure is not None
    assert "copy" not in _kinds(handed.structure.root)
    assert len(handed.criteria) == 6
    assert state.operational_spec_draft.structure is not None
    assert "copy" in _kinds(state.operational_spec_draft.structure.root)
