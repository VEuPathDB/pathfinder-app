"""Site help's script for the deterministic test model.

Seven arcs for the site-help agent: a fixed reply to the check prompt, one
local tool call for a question about the sites, one for a question about the
organisms, one call to each of the two tools a declared source serves, an
answer that names what the thread asked for earlier, and an echo for anything
else.
"""

from __future__ import annotations

from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    ScriptedPart,
    current_turn,
    has_any,
    last_user_text,
    scripted_call,
    scripted_text,
    tool_return_parts,
    user_texts,
)
from pydantic import BaseModel, ConfigDict
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from pathfinder.assistants.site_help.organisms import OrganismSummary

SITE_HELP = "site_help"
LIST_SITES_TOOL = "list_veupathdb_sites"
DESCRIBE_SITE_TOOL = "describe_site"

# The prefix is the tool source's declared name, so a served tool answers
# under it.
WDK_RECORD_TYPES_TOOL = "wdk_list_record_types"
WDK_CONTROL_TESTS_TOOL = "wdk_run_control_tests_on_search"
WDK_CONTROL_TESTS_CALL_ID = "call_wdk_control_tests"

CHECK_MARKER = "site help check"
CHECK_REPLY = "Site help is online."
SITES_REPLY = "Those are the VEuPathDB sites I can point you around."
RECORD_TYPES_PROMPT = "what record types does plasmodb serve"
RECORD_TYPES_REPLY = "Those are the record types that site serves."
CONTROL_TESTS_PROMPT = "run a control test on the molecular weight search"
CONTROL_TESTS_REPLY = "The control test is done."
SCRIPT_SITE = "plasmodb"
CONTROL_TESTS_SEARCH = "GenesByMolecularWeight"

ORGANISMS_PROMPT = "which strains does this site cover"
ORGANISMS_PREFIX = "That site covers "
NO_ORGANISMS_REPLY = "That site declares no organisms."

PROCEED_PROMPT = "Yes, please proceed."
PROCEED_PREFIX = "Proceeding with: "
NOTHING_TO_PROCEED_REPLY = "What would you like me to proceed with?"

_SITES_MARKERS = ("which sites", "what sites", "list the sites")
_ORGANISM_MARKERS = ("which strains", "which organisms", "what organisms")
_RECORD_TYPE_MARKERS = ("record types",)
_CONTROL_TEST_MARKERS = ("control test",)
_PROCEED_MARKERS = ("please proceed", "go ahead")

_ROLES: tuple[RoleMarkers, ...] = (
    RoleMarkers(
        role=SITE_HELP,
        markers=frozenset({LIST_SITES_TOOL, DESCRIBE_SITE_TOOL}),
    ),
)


_REPLY_AFTER: dict[str, str] = {
    LIST_SITES_TOOL: SITES_REPLY,
    WDK_RECORD_TYPES_TOOL: RECORD_TYPES_REPLY,
    WDK_CONTROL_TESTS_TOOL: CONTROL_TESTS_REPLY,
}


def _control_tests_call() -> ToolCallPart:
    """One fixed call id, so a test can answer the approval card it raises."""
    return ToolCallPart(
        tool_name=WDK_CONTROL_TESTS_TOOL,
        args={
            "site_id": SCRIPT_SITE,
            "target_search_name": CONTROL_TESTS_SEARCH,
            "target_parameters": {},
            "positive_controls": ["PF3D7_1222600"],
        },
        tool_call_id=WDK_CONTROL_TESTS_CALL_ID,
    )


class _DescribedSite(BaseModel):
    """The organisms one describe call answered with."""

    model_config = ConfigDict(extra="ignore")

    organisms: list[OrganismSummary] = []


def _named_organism(organism: OrganismSummary) -> str:
    """One species, with its strain count when the site lists strains."""
    if not organism.strain_count:
        return organism.species
    plural = "strain" if organism.strain_count == 1 else "strains"
    return f"{organism.species} ({organism.strain_count} {plural})"


def _organisms_reply(part: ToolReturnPart) -> str:
    """Name every species the describe call returned, with its strain count."""
    described = _DescribedSite.model_validate(part.content, from_attributes=True)
    if not described.organisms:
        return NO_ORGANISMS_REPLY
    named = ", ".join(_named_organism(one) for one in described.organisms)
    return f"{ORGANISMS_PREFIX}{named}."


def _proceed_reply(messages: list[ModelMessage]) -> str:
    """Name the request the thread already made, when the thread carries one."""
    earlier = user_texts(messages)[:-1]
    if not earlier:
        return NOTHING_TO_PROCEED_REPLY
    return f"{PROCEED_PREFIX}{earlier[-1]}"


def _tool_call_for(lowered: str) -> ScriptedPart | None:
    """The tool the markers in the user's text call, or None for no marker."""
    if has_any(lowered, _ORGANISM_MARKERS):
        return scripted_call(DESCRIBE_SITE_TOOL, {"site_id": SCRIPT_SITE})
    if has_any(lowered, _SITES_MARKERS):
        return scripted_call(LIST_SITES_TOOL, {})
    if has_any(lowered, _CONTROL_TEST_MARKERS):
        return _control_tests_call()
    if has_any(lowered, _RECORD_TYPE_MARKERS):
        return scripted_call(WDK_RECORD_TYPES_TOOL, {"site_id": SCRIPT_SITE})
    return None


def _marker_script(messages: list[ModelMessage], lowered: str) -> ScriptedPart | None:
    """The part the markers in the user's text select, or None for no marker."""
    if CHECK_MARKER in lowered:
        return scripted_text(CHECK_REPLY)
    if has_any(lowered, _PROCEED_MARKERS):
        return scripted_text(_proceed_reply(messages))
    return _tool_call_for(lowered)


def _site_help_script(messages: list[ModelMessage]) -> ScriptedPart:
    turn = current_turn(messages)
    for part in tool_return_parts(turn):
        if part.tool_name == DESCRIBE_SITE_TOOL:
            return scripted_text(_organisms_reply(part))
        if part.tool_name in _REPLY_AFTER:
            return scripted_text(_REPLY_AFTER[part.tool_name])
    text = last_user_text(turn)
    marked = _marker_script(messages, text.lower())
    return marked if marked is not None else scripted_text(f"[mock] {text}")


def _unknown_agent_script(messages: list[ModelMessage]) -> ScriptedPart:
    """An agent offering no site-help tool lands here. The conversation-title
    agent is one, and its prompt carries the user's message on the last line.
    """
    lines = last_user_text(messages).splitlines()
    return scripted_text(lines[-1] if lines else "")


_SCRIPTS: dict[str, RoleScript] = {SITE_HELP: _site_help_script}

SITE_HELP_SCRIPT = ScriptedModel(
    roles=_ROLES,
    scripts=_SCRIPTS,
    unknown=_unknown_agent_script,
)


def build_site_help_mock() -> FunctionModel:
    return SITE_HELP_SCRIPT.as_function_model()


__all__ = [
    "CHECK_MARKER",
    "CHECK_REPLY",
    "CONTROL_TESTS_PROMPT",
    "CONTROL_TESTS_REPLY",
    "CONTROL_TESTS_SEARCH",
    "DESCRIBE_SITE_TOOL",
    "LIST_SITES_TOOL",
    "NOTHING_TO_PROCEED_REPLY",
    "NO_ORGANISMS_REPLY",
    "ORGANISMS_PREFIX",
    "ORGANISMS_PROMPT",
    "PROCEED_PREFIX",
    "PROCEED_PROMPT",
    "RECORD_TYPES_PROMPT",
    "RECORD_TYPES_REPLY",
    "SCRIPT_SITE",
    "SITES_REPLY",
    "SITE_HELP_SCRIPT",
    "WDK_CONTROL_TESTS_CALL_ID",
    "WDK_CONTROL_TESTS_TOOL",
    "WDK_RECORD_TYPES_TOOL",
    "build_site_help_mock",
]
