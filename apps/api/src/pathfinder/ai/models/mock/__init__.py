"""The deterministic test model: role detection and arc routing.

A role is read from the tools an agent offers. The arc is the one the turn's
message names with an ``[[arc:<name>]]`` token; each role then plays that
arc's script, after any wrong call a ``[[fault:<name>]]`` token inserts.
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
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from pathfinder.ai.conversation.gene_list_marker import parse_gene_list_marker
from pathfinder.ai.models.mock.arc import Arc, Role, Script
from pathfinder.ai.models.mock.directive import ECHO, ArcDirective, directive_of
from pathfinder.ai.models.mock.faults import fault_call, without_fault_calls
from pathfinder.ai.models.mock.lead_flow import classified_this_turn
from pathfinder.ai.models.mock.registry import arc_named

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
    RoleMarkers(role="frame", markers=frozenset({"set_criterion", "set_structure"})),
    RoleMarkers(role="verification", markers=frozenset({"run_control_tests_on_step"})),
    RoleMarkers(
        role="execution", markers=frozenset({"update_leaf_params", "replace_subtree"})
    ),
)


def turn_directive(messages: list[ModelMessage]) -> ArcDirective:
    """The arc and fault the turn's message names. A run resumed with no
    message of its own reads the token of the newest message that has one."""
    directive = directive_of(current_user_text.get())
    if directive.arc != ECHO:
        return directive
    named = (directive_of(text) for text in reversed(user_texts(messages)))
    return next((found for found in named if found.arc != ECHO), directive)


def _lead_arc(messages: list[ModelMessage], directive: ArcDirective) -> Arc:
    """A resolved consult resumes its build, and an attached gene list with no
    token is the attachment arc, since a file cannot carry a token."""
    if deferred_tool_resolved(messages, "consult_user"):
        return arc_named("consult")
    attached = parse_gene_list_marker(joined_user_text(messages)) is not None
    if directive.arc == ECHO and attached:
        return arc_named("attachment")
    return arc_named(directive.arc)


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


def _unmarked(messages: list[ModelMessage]) -> ToolCallPart:
    """The script for a step whose tool list names no role.

    A turn the classification put out of scope is offered no tool at all, so
    the role table has nothing to read and the Lead's own arc answers it.
    """
    if classified_this_turn(messages):
        return role_script("lead")(messages)
    return terminal_call({})


PATHFINDER_SCRIPT = ScriptedModel(
    roles=_ROLES,
    scripts={
        role: role_script(role)
        for role in ("lead", "frame", "verification", "execution")
    },
    unknown=_unmarked,
)


def get_mock_model() -> FunctionModel:
    return PATHFINDER_SCRIPT.as_function_model()


__all__ = ["PATHFINDER_SCRIPT", "get_mock_model", "role_script", "turn_directive"]
