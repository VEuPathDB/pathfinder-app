"""The deterministic test model: role detection and arc routing.

A role is read from the tools an agent offers. The arc is the one the turn's
message names with an ``[[arc:<name>]]`` token; each role then plays that
arc's script, after any wrong call a ``[[fault:<name>]]`` token inserts. The
turn's words are read as the arc declares, before the Lead runs.
"""

from __future__ import annotations

from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    current_user_text,
    deferred_tool_resolved,
    joined_user_text,
    terminal_call,
    user_texts,
)
from pydantic_ai.messages import ModelMessage, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pathfinder.ai.audit.mock_investigation import (
    INVESTIGATOR,
    PSEUDOGENE_CALL,
    investigator_script,
)
from pathfinder.ai.models.mock.arc import Arc, Role, Script
from pathfinder.ai.models.mock.consult_arc import CONSULT
from pathfinder.ai.models.mock.directive import ArcDirective
from pathfinder.ai.models.mock.faults import fault_call, without_fault_calls
from pathfinder.ai.models.mock.lead_flow import is_the_leads_run
from pathfinder.ai.models.mock.registry import arc_named
from pathfinder.ai.models.mock.turn_arc import lead_arc_name, standing_directive

# Ordered: the first role whose markers intersect the agent's tool names wins.
# The Lead's dispatch tools appear on no sub-agent. A tool that needs approval
# is left out of the tools an agent offers, so none keys a role.
_ROLES: tuple[RoleMarkers, ...] = (
    RoleMarkers(
        role="lead",
        markers=frozenset(
            {
                "frame_problem",
                "build_strategy",
                "verify_strategy",
                "read_ledger_section",
            }
        ),
    ),
    RoleMarkers(role="explore", markers=frozenset({"propose_readings"})),
    RoleMarkers(role="frame", markers=frozenset({"set_criterion", "set_structure"})),
    RoleMarkers(role="verification", markers=frozenset({"run_control_tests_on_step"})),
    RoleMarkers(
        role="execution", markers=frozenset({"update_leaf_params", "replace_subtree"})
    ),
    RoleMarkers(role=INVESTIGATOR, markers=frozenset({PSEUDOGENE_CALL})),
)


def turn_directive(messages: list[ModelMessage]) -> ArcDirective:
    """The arc and fault the turn's message names. A run resumed with no
    message of its own reads the token of the newest message that has one."""
    return standing_directive(current_user_text.get(), user_texts(messages))


def _lead_arc(messages: list[ModelMessage], directive: ArcDirective) -> Arc:
    """A resolved consult resumes its build, and an attached gene list with no
    token is the attachment arc, since a file cannot carry a token."""
    named = lead_arc_name(
        directive,
        card_answered=deferred_tool_resolved(messages, CONSULT),
        texts=joined_user_text(messages),
    )
    return arc_named(named)


def role_script(role: Role) -> Script:
    """The script a role plays: the arc's next call, or the wrong call a fault
    makes in its place."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        directive = turn_directive(messages)
        seen = without_fault_calls(messages)
        arc = _lead_arc(seen, directive) if role == "lead" else arc_named(directive.arc)
        intended = arc.script(role)(seen)
        wrong = fault_call(directive.fault, role, messages, intended)
        return intended if wrong is None else wrong

    return script


def explore_script(messages: list[ModelMessage]) -> ToolCallPart | TextPart:
    return arc_named(turn_directive(messages).arc).explore(messages)


def _unmarked(messages: list[ModelMessage]) -> ToolCallPart:
    """The script for a step whose tool list names no role.

    A turn the reading put out of scope offers the Lead no tool at all, so
    the role table has nothing to read and the Lead's own arc answers it.
    """
    if is_the_leads_run(messages):
        return role_script("lead")(messages)
    return terminal_call({})


PATHFINDER_SCRIPT = ScriptedModel(
    roles=_ROLES,
    scripts={
        **{
            role: role_script(role)
            for role in ("lead", "frame", "verification", "execution")
        },
        "explore": explore_script,
        INVESTIGATOR: investigator_script,
    },
    unknown=_unmarked,
)


def get_mock_model() -> FunctionModel:
    return PATHFINDER_SCRIPT.as_function_model()


__all__ = ["PATHFINDER_SCRIPT", "get_mock_model", "role_script", "turn_directive"]
