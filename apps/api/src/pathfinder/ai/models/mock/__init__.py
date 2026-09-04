"""Role detection and the sub-agent scripts of the deterministic test model.

The role table maps an agent's tool names onto the script that answers for it.
Sub-agents emit their typed delta via ``final_result``. The Lead's arcs live in
``arcs``; the canned FRAME specs live in ``specs``.
"""

from __future__ import annotations

from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    called_tool_parts,
    current_scope_id,
    current_user_text,
    has_any,
    last_user_text,
    scripted_call,
    terminal_call,
    tool_return_parts,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pathfinder.ai.models.mock.arcs import (
    FEEDBACK_PROSE,
    LOOP_CALL_ARGS,
    LOOP_MARKERS,
    SUCCESS_PROSE,
    lead_script,
    spec_for,
    verification_succeeds,
)
from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    SpecPlan,
    alt_organism_for,
    criterion_replies,
    edit_frame_call,
    frame_call,
    verification_delta,
)

LEAD = "lead"
FRAME = "frame"
VERIFICATION = "verification"
EXECUTION = "execution"

# Ordered: the first role whose markers intersect the agent's tool names wins.
# Lead is first: its dispatch tools are unique to the Lead and never appear on a
# sub-agent. (Do NOT key the Lead on consult_user: approval-required deferred
# tools are excluded from AgentInfo.function_tools.)
_ROLES: tuple[RoleMarkers, ...] = (
    RoleMarkers(
        role=LEAD,
        markers=frozenset(
            {
                "frame_problem",
                "build_strategy",
                "verify_strategy",
                "read_ledger_section",
            }
        ),
    ),
    RoleMarkers(role=FRAME, markers=frozenset({"set_criterion", "set_structure"})),
    RoleMarkers(role=VERIFICATION, markers=frozenset({"run_control_tests_on_step"})),
    RoleMarkers(
        role=EXECUTION, markers=frozenset({"update_leaf_params", "replace_subtree"})
    ),
)


def _active_spec() -> SpecPlan:
    return spec_for(current_user_text.get(), current_scope_id.get())


def _criterion_replies(messages: list[ModelMessage]) -> list[CriterionReply]:
    return criterion_replies(tool_return_parts(messages))


def _frame_script(messages: list[ModelMessage]) -> ToolCallPart:
    if has_any(current_user_text.get().lower(), LOOP_MARKERS):
        return scripted_call("list_searches", LOOP_CALL_ARGS)
    work_order = last_user_text(messages)
    if work_order.startswith("EDIT work order"):
        return edit_frame_call(
            work_order,
            alt_organism_for(current_scope_id.get()),
            called_tool_parts(messages),
            _criterion_replies(messages),
        )
    return frame_call(
        _active_spec(),
        called_tool_parts(messages),
        _criterion_replies(messages),
    )


def _verification_script(messages: list[ModelMessage]) -> ToolCallPart:
    del messages
    success = verification_succeeds(current_user_text.get())
    prose = SUCCESS_PROSE if success else FEEDBACK_PROSE
    return terminal_call(verification_delta(success=success, prose=prose))


def _execution_script(messages: list[ModelMessage]) -> ToolCallPart:
    del messages
    return terminal_call({"actionsTaken": ["[mock] recovery"], "followUpNeeded": False})


def _silent_script(messages: list[ModelMessage]) -> ToolCallPart:
    del messages
    return terminal_call({})


_SCRIPTS: dict[str, RoleScript] = {
    LEAD: lead_script,
    FRAME: _frame_script,
    VERIFICATION: _verification_script,
    EXECUTION: _execution_script,
}

PATHFINDER_SCRIPT = ScriptedModel(
    roles=_ROLES,
    scripts=_SCRIPTS,
    unknown=_silent_script,
)


def get_mock_model() -> FunctionModel:
    return PATHFINDER_SCRIPT.as_function_model()


__all__ = ["PATHFINDER_SCRIPT", "get_mock_model"]
