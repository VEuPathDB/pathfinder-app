"""What the Lead reads before it acts.

One render per pinned instruction: the message it answers, the intent it
classified, the spec it frames against, the EDA filter sheet it holds open,
the ledger it decides from, and what moved on the thread since it last
answered.
"""

from __future__ import annotations

import json

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai import RunContext
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyStep, subtree_ids
from veupathdb_mcp.catalog import EDA_DATASET_ID_PARAM

from pathfinder.ai.agents.pinned_sheets import blocks_within_budget
from pathfinder.ai.lead._delete_rules import (
    roots_by_size,
    steps_outside_the_strategy,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent_gate import turn_builds, turn_is_off_topic
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.eda_parts import EdaFilterSheetEntry, OpenEdaSheet
from pathfinder.domain.strategy.operational_spec import (
    DroppedCriterion,
    OperationalSpec,
    eda_backed_drops,
)
from pathfinder.domain.strategy.session import StrategyGraph, strategy_root_id
from pathfinder.domain.strategy.types import SyncStateProtocol

__all__ = [
    "eda_route_blocks",
    "pinned_detached_steps",
    "pinned_eda_sheet",
    "pinned_ledger_summary",
    "pinned_operational_spec",
    "pinned_turn_briefing",
    "pinned_user_intent",
    "pinned_user_prompt",
]

# A thread holds a strategy plus leftovers only once it has more than one root.
_SEVERAL_ROOTS = 2

_EDA_SHEET_HEADER = (
    "# Open EDA filter sheet\n"
    "The block below stays here until its subset is applied. Copy entityId, "
    "variableId and filterType from one entry into the filters array of "
    "`set_eda_filters`. A string value must be copied from the vocabulary "
    "shown here."
)
_EDA_CUT_NOTE = (
    "the pinned sheet is over budget, so this variable holds no values; ask "
    "preview_eda_subset for its distribution to see the values the current "
    "subset holds"
)


def _eda_block(sheet: OpenEdaSheet) -> str:
    entries = [entry.model_dump(by_alias=True, mode="json") for entry in sheet.entries]
    return f"### filter sheet for {sheet.dataset_id}\n{json.dumps(entries)}"


def _eda_block_without_values(sheet: OpenEdaSheet) -> str:
    """The same block with the vocabularies dropped, names and examples kept."""
    return _eda_block(
        sheet.model_copy(update={"entries": _without_values(sheet.entries)})
    )


def _without_values(
    entries: list[EdaFilterSheetEntry],
) -> list[EdaFilterSheetEntry]:
    return [
        entry.model_copy(update={"vocabulary": [], "vocabulary_note": _EDA_CUT_NOTE})
        if entry.vocabulary_total
        else entry
        for entry in entries
    ]


def pinned_eda_sheet(ctx: RunContext[LeadDeps]) -> str | None:
    """The EDA filter sheet the thread has open, with the values it copies from."""
    sheet = ctx.deps.state.domain.open_eda_sheet
    if sheet is None:
        return None
    blocks = blocks_within_budget(
        [sheet], _eda_block, _eda_block_without_values, cut_last=True
    )
    return "\n\n".join([_EDA_SHEET_HEADER, *blocks])


def pinned_ledger_summary(ctx: RunContext[LeadDeps]) -> str:
    """Builds the compact ledger summary. It is derived on each render."""
    ledger = derive_ledger(
        ctx.deps.state,
        ctx.deps.intent,
        phase_stop=ctx.deps.last_phase_stop,
    )
    return ledger.render_summary()


def pinned_operational_spec(ctx: RunContext[LeadDeps]) -> str | None:
    """Renders the operational spec, which the Lead reads to decide build readiness."""
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return "## Operational Spec\nNot framed yet. Call ``frame_problem``."
    lines = [
        "## Operational Spec",
        f"- goal: {spec.interpreted_goal or spec.goal}",
        f"- ready_to_build: {spec.ready_to_build}",
    ]
    for c in spec.criteria:
        slots = [s.param_name for s in c.open_params]
        line = f"  - [{c.id}] {c.text[:60]} -> {c.search_name or '(UNBOUND)'}"
        if slots:
            line += f" | open: {slots}"
        lines.append(line)
    if spec.dropped:
        lines.append("  dropped: " + "; ".join(d.text for d in spec.dropped))
    return "\n".join(lines)


def pinned_user_intent(ctx: RunContext[LeadDeps]) -> str | None:
    intent = ctx.deps.intent
    if intent is None:
        return (
            "## User Intent\nNot classified yet. Call ``classify_user_intent`` first."
        )
    lines = [
        "## User Intent",
        f"- classification: {intent.classification.value}",
        f"- inferred goal: {intent.inferred_goal}",
    ]
    if intent.is_differential and intent.differential_sides:
        lines.append(f"- differential sides: {intent.differential_sides}")
    if intent.referenced_step_ids:
        lines.append(f"- referenced steps: {intent.referenced_step_ids}")
    if intent.referenced_strategy_ids:
        lines.append(
            f"- referenced strategies: {intent.referenced_strategy_ids}",
        )
    return "\n".join(lines)


_OFF_TOPIC_REDIRECT = (
    "## This turn is out of scope\n"
    "Answer in two sentences and call no tool. Say that PathFinder builds, "
    "edits and checks search strategies on the VEuPathDB databases and runs "
    "enrichment, EDA and exports on what they return, then invite the user to "
    "put their question in those terms. Write nothing else: no code, no draft, "
    "and no answer to what was asked."
)


def _reads_the_dataset(step: StrategyStep, dataset_id: str) -> bool:
    """Whether this step's search runs on that EDA dataset."""
    value = step.parameters.get(EDA_DATASET_ID_PARAM)
    return value is not None and to_wire(value) == dataset_id


def _reachable(
    graph: StrategyGraph | None, sync_state: SyncStateProtocol | None
) -> set[str]:
    """The steps the strategy reaches from its root.

    The root the last push named answers when there is one, and the structural
    root stands in otherwise, which is where the export is placed.
    """
    if graph is None:
        return set()
    root = strategy_root_id(graph, sync_state) or graph.primary_root_id()
    return set(subtree_ids(root or "", graph.steps))


def _steps_on_the_dataset(
    graph: StrategyGraph | None, dataset_id: str, reachable: set[str]
) -> tuple[list[str], list[str]]:
    """The steps reading this dataset, inside the strategy and outside it."""
    if graph is None:
        return [], []
    found = sorted(
        step_id
        for step_id, step in graph.steps.items()
        if _reads_the_dataset(step, dataset_id)
    )
    return (
        [step_id for step_id in found if step_id in reachable],
        [step_id for step_id in found if step_id not in reachable],
    )


def _free_slot(
    graph: StrategyGraph | None, reachable: set[str]
) -> tuple[str, str] | None:
    """The first input of a combine of the strategy that holds no step.

    Only a combine the strategy reaches counts: an export into a detached one
    lands outside the strategy.
    """
    if graph is None:
        return None
    for step_id in sorted(reachable):
        step = graph.steps[step_id]
        if step.operator is None:
            continue
        if step.primary_input_id is None:
            return step_id, "primary"
        if step.secondary_input_id is None:
            return step_id, "secondary"
    return None


_JOIN_TAIL = 'use "MINUS" when the criterion excludes genes.'


def _export_call(
    graph: StrategyGraph | None,
    held: list[str],
    reachable: set[str],
    *,
    pending: bool,
) -> str:
    """The create_eda_step call that puts the export where it belongs."""
    if held:
        return (
            f'4. create_eda_step(replace_step_id="{held[0]}") - the strategy '
            f"holds {held} for this criterion, and the export takes that "
            f"step's place."
        )
    slot = _free_slot(graph, reachable)
    if slot is not None:
        return (
            f'4. create_eda_step(attach_to_step_id="{slot[0]}", '
            f'slot="{slot[1]}") - that input of the combine is free.'
        )
    root = None if graph is None else graph.primary_root_id()
    if root is not None:
        return (
            f'4. create_eda_step(combine_with_root="INTERSECT") - it joins the '
            f"export to the strategy's root {root}; {_JOIN_TAIL}"
        )
    if pending:
        return (
            f'4. create_eda_step(combine_with_root="INTERSECT") - once step 0 '
            f"has built the strategy, this joins the export to its root; "
            f"{_JOIN_TAIL}"
        )
    return "4. create_eda_step() - there is no strategy for the export to join yet."


def _criteria_with_no_step(
    spec: OperationalSpec, graph: StrategyGraph | None
) -> list[str]:
    """The bound criteria the strategy holds no step for, in spec order."""
    steps = set() if graph is None else set(graph.steps)
    return [c.id for c in spec.criteria if c.bound and c.id not in steps]


def _eda_route_block(
    graph: StrategyGraph | None,
    sync_state: SyncStateProtocol | None,
    dropped: DroppedCriterion,
    pending: list[str],
) -> str:
    """The calls that build one dropped EDA-backed criterion, in order."""
    dataset = dropped.eda_dataset_id
    reachable = _reachable(graph, sync_state)
    held, elsewhere = _steps_on_the_dataset(graph, dataset or "", reachable)
    lines = [
        f"## Build the EDA criterion: {dropped.text}",
        (
            "The framing pass dropped it because its search is EDA-backed, so "
            "only these calls build it. Make them this turn, in this order:"
        ),
    ]
    if pending:
        lines.append(
            f"0. build_strategy for the remaining criteria ({pending}) so the "
            f"export has a strategy to join",
        )
    lines.extend(
        [
            f'1. open_eda_analysis(dataset_id="{dataset}", purpose=...)',
            "2. set_eda_filters - once for the sheet, once with the filters array",
            "3. preview_eda_subset",
            _export_call(graph, held, reachable, pending=bool(pending)),
        ],
    )
    if elsewhere:
        lines.append(
            f"Steps on this dataset that stand outside the strategy: {elsewhere}.",
        )
    lines.append(
        "Never ask the user for an analysis specification, and never answer "
        "that this criterion cannot be built or mapped.",
    )
    return "\n".join(lines)


def eda_route_blocks(ctx: RunContext[LeadDeps]) -> list[str]:
    """One block per dropped criterion the EDA tools still have to build."""
    spec = ctx.deps.state.domain.operational_spec
    dropped = eda_backed_drops(spec)
    if not dropped or spec is None or not turn_builds(ctx.deps):
        return []
    session = ctx.deps.runtime.strategy_session
    graph = session.get_graph(None)
    pending = _criteria_with_no_step(spec, graph)
    return [
        _eda_route_block(graph, session.sync_state, entry, pending) for entry in dropped
    ]


_WIRE_OR_CLEAR = (
    "wire one in with create_eda_step(replace_step_id=...)/attach and build, "
    "or call clear_strategy to start the thread over."
)


def _named(graph: StrategyGraph, step_ids: list[str]) -> str:
    """Each step id with the name the researcher reads it by, when it has one."""
    return "; ".join(
        f"{step_id} ({graph.steps[step_id].display_name})"
        if graph.steps[step_id].display_name
        else step_id
        for step_id in step_ids
    )


def _roots_no_push_named(graph: StrategyGraph) -> str:
    """The roots of a thread whose strategy is not known, and what takes them.

    None of them is the strategy, so none of them is loose either. A root of
    one step is the one a delete still takes.
    """
    lone = sorted(sid for sid in graph.roots if graph.subtree_size(sid) == 1)
    takeable = (
        f" delete_step(step_id) (the user approves) takes a root of one step: "
        f"{_named(graph, lone)}."
        if lone
        else ""
    )
    return (
        f"This thread holds {count_noun(len(graph.roots), 'root')} and no push "
        f"says which is the strategy: {roots_by_size(graph)}.{takeable} A root "
        f"of more than one step is refused, so {_WIRE_OR_CLEAR}"
    )


def pinned_detached_steps(ctx: RunContext[LeadDeps]) -> str | None:
    """The steps outside the strategy, or the roots it cannot be told from.

    Every way out is a tool a turn that does not build cannot reach, so the
    pin holds its peace on one.
    """
    if not turn_builds(ctx.deps):
        return None
    session = ctx.deps.runtime.strategy_session
    graph = session.get_graph(None)
    if graph is None or len(graph.roots) < _SEVERAL_ROOTS:
        return None
    if strategy_root_id(graph, session.sync_state) is None:
        return _roots_no_push_named(graph)
    loose = steps_outside_the_strategy(graph, session.sync_state)
    if not loose:
        return None
    return (
        f"Steps outside the strategy: {_named(graph, loose)}. Remove one with "
        f"delete_step(step_id) (the user approves), or wire it in with "
        f"create_eda_step(replace_step_id=...)/attach."
    )


def pinned_turn_briefing(ctx: RunContext[LeadDeps]) -> str | None:
    """What moved on the thread since the Lead last answered, the EDA criteria
    it still has to build, and the redirect an out-of-scope turn answers with.

    The catch-up is windowed on the last answer, so a turn that drops it drops
    it for good. The redirect is last, because it is what this turn does.
    """
    blocks = [
        ctx.deps.state.domain.turn_briefing,
        pinned_detached_steps(ctx),
        *eda_route_blocks(ctx),
    ]
    if turn_is_off_topic(ctx.deps):
        blocks.append(_OFF_TOPIC_REDIRECT)
    return "\n\n".join(block for block in blocks if block) or None


def pinned_user_prompt(ctx: RunContext[LeadDeps]) -> str | None:
    prompt = ctx.deps.state.user_prompt
    if not prompt:
        return None
    return f"## User's latest message\n{prompt}"
