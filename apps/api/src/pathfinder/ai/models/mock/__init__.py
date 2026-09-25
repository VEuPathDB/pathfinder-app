"""Role detection and the sub-agent scripts of the deterministic test model.

The role table maps an agent's tool names onto the script that answers for it.
Sub-agents emit their typed delta via ``final_result``. The Lead's arcs live in
``arcs`` and ``prose_arcs``; the canned FRAME specs live in ``specs``.
"""

from __future__ import annotations

from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    current_scope_id,
    current_user_text,
    has_any,
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
    classified_this_turn,
    lead_script,
    spec_for,
    verification_succeeds,
)
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.separation_arc import adopted_check
from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    SpecPlan,
    alt_organism_for,
    criterion_replies,
    edit_frame_call,
    frame_call,
    organism_for,
    verification_delta,
)
from pathfinder.ai.models.mock.verify_arc import review, review_call

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
    work_order = head_work_order(messages)
    called = acted_tool_names(messages)
    replies = _criterion_replies(messages)
    if work_order.startswith("EDIT work order"):
        return edit_frame_call(
            work_order,
            alt_organism_for(current_scope_id.get()),
            called,
            replies,
        )
    return frame_call(_active_spec(), called, replies)


# A request that names its controls is checked against these before the digest.
_CONTROLS_MARKERS = ("against my controls",)
_CONTROL_TEST = "run_control_tests_on_search"
_POSITIVE_CONTROLS = ("PF3D7_0102600", "PF3D7_0709000", "PF3D7_1133400")
_NEGATIVE_CONTROLS = ("TGME49_205250",)


def _control_test_call() -> ToolCallPart:
    """A test of the single-leaf spec's search, the one step a mock build pushes."""
    organism = organism_for(current_scope_id.get())
    return scripted_call(
        _CONTROL_TEST,
        {
            "target_search_name": "GenesByTaxon",
            "target_parameters": {
                "organism": {"type": "multi-pick-vocabulary", "values": [organism]}
            },
            "positive_controls": list(_POSITIVE_CONTROLS),
            "negative_controls": list(_NEGATIVE_CONTROLS),
        },
    )


def _verification_script(messages: list[ModelMessage]) -> ToolCallPart:
    adopted = adopted_check(messages)
    if adopted is not None:
        return adopted
    text = current_user_text.get()
    if has_any(text.lower(), _CONTROLS_MARKERS) and _CONTROL_TEST not in (
        acted_tool_names(messages)
    ):
        return _control_test_call()
    reading = review_call(messages)
    if reading is not None:
        return reading
    success = verification_succeeds(text)
    prose = SUCCESS_PROSE if success else FEEDBACK_PROSE
    organism = organism_for(current_scope_id.get())
    return terminal_call(
        verification_delta(
            success=success, prose=prose, review=review(messages, organism)
        )
    )


def _execution_script(messages: list[ModelMessage]) -> ToolCallPart:
    del messages
    return terminal_call({"actionsTaken": ["[mock] recovery"], "followUpNeeded": False})


def _unmarked_script(messages: list[ModelMessage]) -> ToolCallPart:
    """The script for a step whose tool list names no role.

    A turn the classification put out of scope is offered no tool at all, so
    the role table has nothing to read and the Lead's own arc answers it.
    """
    if classified_this_turn(messages):
        return lead_script(messages)
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
    unknown=_unmarked_script,
)


def get_mock_model() -> FunctionModel:
    return PATHFINDER_SCRIPT.as_function_model()


__all__ = ["PATHFINDER_SCRIPT", "get_mock_model"]
