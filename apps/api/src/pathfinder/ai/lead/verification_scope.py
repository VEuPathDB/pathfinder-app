"""What the researcher asked verification to answer, read from the thread:
the request, the requirements, the words no search states, and the counts
this turn's edit moved."""

from __future__ import annotations

from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_review import ReviewRecord, breached_rows
from pathfinder.services.gene_records.read import gene_record_url


def review_record(deps: LeadDeps, messages: list[str]) -> ReviewRecord:
    """What this turn holds that the check's review is held to."""
    live = frozenset(deps.runtime.strategy_session.wdk_step_ids())
    return ReviewRecord(
        messages=messages,
        requirements=deps.state.domain.requirements,
        spec=deps.state.domain.operational_spec,
        read_as=deps.state.turn_markers.retrieved_as,
        record_url=lambda gene_id: gene_record_url(deps.runtime.site_id, gene_id),
        column_fits=[
            fit
            for fit in deps.state.turn_markers.column_fits
            if fit.wdk_step_id in live
        ],
    )


def _counts_before(deps: LeadDeps) -> list[str]:
    """One line per step this turn's write moved, in tree order."""
    session = deps.runtime.strategy_session
    graph = session.get_graph(None)
    root_id = None if graph is None else graph.primary_root_id()
    if graph is None or root_id is None or session.sync_state is None:
        return []
    counts = session.sync_state.step_counts
    markers = deps.state.turn_markers
    lines: list[str] = []
    for step in graph.steps_in_tree_order(root_id):
        now = counts.get(step.id)
        held = markers.count_before(step.id, now)
        if held is None:
            continue
        lines.append(
            f"[{step.id}] {step.display_name or step.display_label}: {held} before "
            f"this turn's edit, {now if now is not None else 'not counted'} now"
        )
    return lines


def verification_scope(deps: LeadDeps, *, check_id: str) -> VerificationScope:
    """The request this turn answers and the check that answers it, as VERIFY reads them."""
    messages = deps.state.researcher_messages()
    spec = deps.state.domain.operational_spec
    ledger = derive_ledger(deps.state, deps.intent)
    return VerificationScope(
        messages=messages,
        stated=[line.removeprefix("- ") for line in ledger.constraints.render_stated()],
        unexpressed=[
            f"'{text.word}' in [{text.criterion_id or 'dropped'}] {text.stated_in}"
            for text in (spec.unexpressed() if spec is not None else [])
        ],
        breaches=[row.note for row in breached_rows(review_record(deps, messages))],
        before=_counts_before(deps),
        check_id=check_id,
        last_card=deps.state.domain.card_of_the_strategy(),
        controls=deps.state.domain.attached_controls,
        control_sets=list(deps.state.domain.control_sets),
    )
