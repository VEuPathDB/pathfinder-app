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

from strategist.ai.models.mock.arc import Arc, Role, Script
from strategist.ai.models.mock.consult_arc import CONSULT
from strategist.ai.models.mock.directive import ArcDirective
from strategist.ai.models.mock.faults import fault_call, without_fault_calls
from strategist.ai.models.mock.lead_flow import is_the_leads_run
from strategist.ai.models.mock.reads import instructions_of
from strategist.ai.models.mock.registry import arc_named
from strategist.ai.models.mock.turn_arc import lead_arc_name, standing_directive

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


_EXPLORE_MARK = "**Explore mode**"


def explore_script(messages: list[ModelMessage]) -> ToolCallPart | TextPart:
    return arc_named(turn_directive(messages).arc).explore(messages)


def _unmarked(messages: list[ModelMessage]) -> ToolCallPart | TextPart:
    """The script for a step whose tool list names no role.

    A turn the reading put out of scope offers the Lead and Explore no tool at
    all, so the role table has nothing to read and the agent's own arc answers it.
    """
    if _EXPLORE_MARK in instructions_of(messages):
        return explore_script(messages)
    if is_the_leads_run(messages):
        return role_script("lead")(messages)
    return terminal_call({})


STRATEGIST_SCRIPT = ScriptedModel(
    roles=_ROLES,
    scripts={
        **{
            role: role_script(role)
            for role in ("lead", "frame", "verification", "execution")
        },
        "explore": explore_script,
    },
    unknown=_unmarked,
)


def get_mock_model() -> FunctionModel:
    return STRATEGIST_SCRIPT.as_function_model()


__all__ = ["STRATEGIST_SCRIPT", "get_mock_model", "role_script", "turn_directive"]
