"""Pinned instructions that describe PathFinder's strategy work: the system
prompt, the in-progress spec, the live graph, the ledger and the searches
FRAME inspected."""

from __future__ import annotations

from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.strategy.graph_model import StrategyStep

from pathfinder.ai.agents.param_vocab_render import render_param_vocab
from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.prompts.loader import load_system_prompt
from pathfinder.domain.strategy.types import SyncStateProtocol


def base_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    return load_system_prompt(include_site_hints=True)


def pinned_frame_workspace(ctx: RunContext[AgentDeps]) -> str | None:
    spec = ctx.deps.agent_state.operational_spec_draft
    if not spec.criteria and not spec.dropped:
        return None
    lines = [
        "# FRAME workspace (in-progress spec)",
        (
            "Values shown here are already bound and are preserved unless the "
            "request changes them."
        ),
    ]
    for c in spec.criteria:
        slots = [s.param_name for s in c.open_params]
        saved = c.saved_strategy_ref
        bound_to = c.search_name or (saved.label if saved is not None else "(UNBOUND)")
        line = f"- [{c.id}] {c.text[:60]} -> {bound_to}"
        if slots:
            line += f" | open: {slots}"
        lines.append(line)
        lines.extend(
            f"    {name}={to_wire(value)}" for name, value in c.resolved_params.items()
        )
    if spec.dropped:
        lines.append("dropped: " + "; ".join(d.text for d in spec.dropped))
    lines.append(
        f"structure_set={spec.structure is not None} "
        f"ready_to_build={spec.ready_to_build}"
    )
    return "\n".join(lines)


_MAX_PARAM_VAL_LEN = 40


def _render_step_header(step_id: str, step: StrategyStep) -> list[str]:
    kind = step.kind.value
    parts: list[str] = [f"{step_id}:"]

    if kind == "combine":
        op = step.operator or "?"
        primary = step.primary_input_id or "?"
        secondary = step.secondary_input_id or "?"
        parts.append(f"{op}({primary}, {secondary})")
    elif kind == "transform":
        parts.append(f"{step.search_name} [transform]")
        input_id = step.primary_input_id or "?"
        parts.append(f"input={input_id}")
    else:
        parts.append(f"{step.search_name} [leaf]")

    if step.display_name:
        parts.append(f'"{step.display_name}"')
    return parts


def _render_step_suffix(
    step_id: str,
    sync_state: SyncStateProtocol | None,
    *,
    is_root: bool,
) -> str:
    count = sync_state.step_counts.get(step_id) if sync_state else None
    wdk_id = sync_state.wdk_step_ids.get(step_id) if sync_state else None
    push_error = sync_state.wdk_push_errors.get(step_id) if sync_state else None
    validation = sync_state.step_validations.get(step_id) if sync_state else None

    suffix_parts: list[str] = []
    if count is not None:
        suffix_parts.append(f"{count:,} genes")
    if wdk_id is not None:
        suffix_parts.append(f"wdk={wdk_id}")
    if is_root:
        suffix_parts.append("root")
    if push_error:
        suffix_parts.append(f"ERROR: {push_error[:60]}")
    if validation and not validation.is_valid:
        general = validation.errors.general if validation.errors else []
        if general:
            suffix_parts.append(f"INVALID: {str(general[0])[:60]}")
        else:
            suffix_parts.append("INVALID")
    if suffix_parts:
        return f"\u2192 {', '.join(suffix_parts)}"
    return ""


def _render_step_params(step: StrategyStep) -> str:
    """Renders the parameters of one step as a single indented line."""
    if not step.parameters:
        return ""
    param_strs: list[str] = []
    for name, value in step.parameters.items():
        wire = to_wire(value)
        if len(wire) > _MAX_PARAM_VAL_LEN:
            wire = wire[: _MAX_PARAM_VAL_LEN - 3] + "..."
        param_strs.append(f"{name}={wire}")
    return "\n  " + ", ".join(param_strs)


def pinned_graph_state(ctx: RunContext[AgentDeps]) -> str | None:
    """Renders the live strategy graph so a tool result does not carry the
    full snapshot."""
    session = ctx.deps.strategy_session
    graph = session.get_graph(None)
    if not graph or not graph.steps:
        return None

    sync_state = session.sync_state
    lines: list[str] = []
    for step_id, step in graph.steps.items():
        parts = _render_step_header(step_id, step)
        suffix = _render_step_suffix(
            step_id, sync_state, is_root=step_id in graph.roots
        )
        if suffix:
            parts.append(suffix)
        line = " ".join(parts)
        if step.kind.value != "combine":
            line += _render_step_params(step)
        lines.append(line)

    header = f"Current strategy graph ({len(graph.steps)} steps):"
    wdk_strategy_id = sync_state.wdk_strategy_id if sync_state else None
    if wdk_strategy_id:
        header += f" wdk_strategy={wdk_strategy_id}"
    return header + "\n\n" + "\n\n".join(lines)


def pinned_ledger(ctx: RunContext[AgentDeps]) -> str | None:
    """The Lead's investigation ledger (curated structured state) — what's
    framed, discovered, planned, built, verified. Read-only shared context so
    a sub-agent knows what's already resolved and doesn't redo or re-ask it."""
    summary = ctx.deps.ledger_summary
    if not summary.strip():
        return None
    return f"## Investigation ledger (read-only)\n{summary}"


def pinned_discovered_searches(ctx: RunContext[AgentDeps]) -> str | None:
    """Render the searches FRAME has inspected so far.

    FRAME's catalog tools commit each search into
    ``agent_state.discovered_searches`` as they inspect it, and it is
    persisted on the graph state so later turns see it too. This is a cache
    of what the catalog returned, not the source of truth for the plan --
    that is the ``OperationalSpec``. Recovery and verification read it to
    know what is available without re-reading FRAME's tool trace. Includes
    vocabulary snapshots captured by ``get_parameter_options`` so values are
    copied verbatim instead of guessed.
    """
    searches = ctx.deps.agent_state.discovered_searches
    if not searches:
        return None
    lines = ["## Discovered searches", ""]
    for name in sorted(searches):
        lines.extend(_render_search(name, searches[name]))
    return "\n".join(lines)


def _render_search(name: str, ov: SearchOverview) -> list[str]:
    out = [f"- `{name}` ({ov.record_type}) — {ov.display_name}"]
    if ov.required_params:
        out.append(f"    required params: {', '.join(ov.required_params)}")
    if ov.param_vocab:
        out.append("    param_vocab (copy values verbatim):")
        for pname in sorted(ov.param_vocab):
            out.extend(render_param_vocab(pname, ov.param_vocab[pname], indent=6))
    return out
