"""What the Lead reads before it acts.

One render per pinned instruction: the message it answers, the intent it
classified, the spec it frames against, the EDA filter sheet it holds open, the ledger it
decides from, and what moved on the thread since it last answered.
"""

from __future__ import annotations

import json

from pydantic_ai import RunContext

from pathfinder.ai.agents.pinned_sheets import blocks_within_budget
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.eda_parts import EdaFilterSheetEntry, OpenEdaSheet

__all__ = [
    "pinned_eda_sheet",
    "pinned_ledger_summary",
    "pinned_operational_spec",
    "pinned_turn_briefing",
    "pinned_user_intent",
    "pinned_user_prompt",
]

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


def pinned_turn_briefing(ctx: RunContext[LeadDeps]) -> str | None:
    """What moved on the thread since the Lead last answered, or nothing."""
    return ctx.deps.state.domain.turn_briefing or None


def pinned_user_prompt(ctx: RunContext[LeadDeps]) -> str | None:
    prompt = ctx.deps.state.user_prompt
    if not prompt:
        return None
    return f"## User's latest message\n{prompt}"
