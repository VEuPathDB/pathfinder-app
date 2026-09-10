"""How reversible each of the Lead's tools is, and the preamble that states it.

The classification is explicit and a unit test holds it complete against the
registered tool set. The preamble text is generated from that map and from the
registry's own markers: ``requires_approval``, ``BUILDING_TOOLS``, the durable
registration and the phase role a dispatch tool carries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import StrEnum

from assistant_core.graph.durable import DURABLE_TOOLS
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS
from pathfinder.ai.lead.sub_agent_tools import TOOL_TO_PHASE_ROLE, LeadDeps


class Reversibility(StrEnum):
    """What undoing one tool's effect costs the researcher."""

    READ = "read"
    IN_STATE = "in_state"
    REVISIONED_WRITE = "revisioned_write"
    UNREVISIONED_WRITE = "unrevisioned_write"
    GATED_DESTRUCTIVE = "gated_destructive"
    DURABLE = "durable"


TOOL_REVERSIBILITY: Mapping[str, Reversibility] = {
    "build_control_set": Reversibility.UNREVISIONED_WRITE,
    "build_strategy": Reversibility.REVISIONED_WRITE,
    "classify_user_intent": Reversibility.IN_STATE,
    "clear_strategy": Reversibility.GATED_DESTRUCTIVE,
    "compare_search_variants": Reversibility.READ,
    "compare_variants_scored": Reversibility.UNREVISIONED_WRITE,
    "consult_user": Reversibility.IN_STATE,
    "create_eda_step": Reversibility.REVISIONED_WRITE,
    "describe_eda_study": Reversibility.READ,
    "edit_strategy": Reversibility.REVISIONED_WRITE,
    "frame_problem": Reversibility.IN_STATE,
    "get_live_strategy_state": Reversibility.READ,
    "import_control_ids_from_gene_set": Reversibility.READ,
    "import_control_ids_from_strategy": Reversibility.READ,
    "list_control_sets": Reversibility.READ,
    "open_eda_analysis": Reversibility.UNREVISIONED_WRITE,
    "preview_eda_subset": Reversibility.READ,
    "read_ledger_section": Reversibility.READ,
    "recover_failed_steps": Reversibility.REVISIONED_WRITE,
    "remember": Reversibility.UNREVISIONED_WRITE,
    "run_eda_compute": Reversibility.DURABLE,
    "search_eda_studies": Reversibility.READ,
    "set_eda_filters": Reversibility.UNREVISIONED_WRITE,
    "verify_strategy": Reversibility.IN_STATE,
}


def registered_tools(
    toolsets: Sequence[AbstractToolset[LeadDeps]],
) -> dict[str, Tool[LeadDeps]]:
    """Every tool the Lead can call, by name, carrying its registry markers."""
    found: dict[str, Tool[LeadDeps]] = {}
    for toolset in toolsets:
        if isinstance(toolset, FunctionToolset):
            found.update(toolset.tools)
    return found


def _named(names: Iterable[str]) -> str:
    return ", ".join(sorted(names))


def _in_class(cls: Reversibility, known: Iterable[str]) -> set[str]:
    names = set(known)
    return {name for name, value in TOOL_REVERSIBILITY.items() if value is cls} & names


def _role(role: str, known: Iterable[str]) -> set[str]:
    names = set(known)
    return {name for name, phase in TOOL_TO_PHASE_ROLE.items() if phase == role} & names


def render_machine_guarantees(tools: Mapping[str, Tool[LeadDeps]]) -> str:
    """The preamble, generated from the map and the registry's markers."""
    known = set(tools)
    approval = {name for name, tool in tools.items() if tool.requires_approval}
    destructive = _in_class(Reversibility.GATED_DESTRUCTIVE, known)
    revisioned = _in_class(Reversibility.REVISIONED_WRITE, known) | destructive
    lines = [
        "## What the machine already guarantees",
        "",
        (
            "These hold on every turn. Do not spend calls checking them, and do not"
            " warn the researcher about a risk this list rules out."
        ),
        "",
        (
            f"- Every write to the strategy appends a revision, and the researcher"
            f" can revert the thread to any earlier one. The tools that write it:"
            f" {_named(revisioned)}."
        ),
        (
            f"- Destructive: {_named(destructive)}. Each appends a revision like"
            f" every other write, so what it clears is recovered by a revert rather"
            f" than lost."
        ),
        (
            f"- Held until the researcher answers: {_named(approval)}. The machine"
            f" asks for each of them, so do not also ask in prose."
        ),
        (
            f"- A success verdict cannot outrank the build: what"
            f" {_named(_role('verification', known))} reports is held down to the"
            f" steps the build recorded before you read it."
        ),
        (
            f"- An undeclared spec change is refused, and the spec the turn started"
            f" from is restored, when the account of an edit does not match what it"
            f" did: {_named(_role('frame', known))}."
        ),
        (
            f"- Run on a worker, so the turn ends and reopens with the result:"
            f" {_named(set(DURABLE_TOOLS) & known)}. Nothing before"
            f" the call runs a second time."
        ),
        (
            f"- Withheld until the turn is classified as one that asks for a build:"
            f" {_named(BUILDING_TOOLS & known)}. One of them missing from your list"
            f" is a classification to redo, never a refusal to report."
        ),
        f"- Change nothing at all: {_named(_in_class(Reversibility.READ, known))}.",
        (
            f"- Change only what this turn holds:"
            f" {_named(_in_class(Reversibility.IN_STATE, known))}."
        ),
        (
            f"- Write outside the strategy's history, so a revert of the strategy"
            f" does not undo them:"
            f" {_named(_in_class(Reversibility.UNREVISIONED_WRITE, known))}."
        ),
        "",
    ]
    return "\n".join(lines)


def machine_guarantees_pin(
    toolsets: Sequence[AbstractToolset[LeadDeps]],
) -> Callable[[], str]:
    """The pinned instruction, rendered once for the agent it belongs to."""
    text = render_machine_guarantees(registered_tools(toolsets))

    def pinned_machine_guarantees() -> str:
        return text

    return pinned_machine_guarantees


__all__ = [
    "TOOL_REVERSIBILITY",
    "Reversibility",
    "machine_guarantees_pin",
    "registered_tools",
    "render_machine_guarantees",
]
