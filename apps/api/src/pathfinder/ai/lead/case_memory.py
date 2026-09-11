"""The case a verified turn leaves behind.

A case records the goal that reached a count and what reached it: the spec, or
the EDA cut a turn exported. A recovery case is added for every search this
thread emptied and this build filled. The key is the content hash, so the same
case written twice is one row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.memory.autowrite import MemoryCandidate
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.tombstones import compute_content_hash

from pathfinder.ai.graph.state import PipelineState, ZeroResultStep
from pathfinder.ai.lead.ledger_sections import render_structure
from pathfinder.domain.eda_thread import EdaAnalysisFacts, EdaExport
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

__all__ = ["collect_case_candidates"]

_NAME_LIMIT = 120
_SUMMARY_LIMIT = 400


def collect_case_candidates(state: PipelineState) -> list[MemoryCandidate]:
    """The cases of one turn: what reached the count, then each recovery.

    A turn reaching a count through an EDA export leaves the export's case; a
    turn reaching it through a spec leaves the spec's, plus its recoveries.
    """
    outcome = state.domain.last_build_outcome
    if outcome is None:
        return []
    export = state.turn_markers.eda_export
    if export is not None:
        # The count came from the export, so the export's case is THE case.
        # A spec the turn framed but never built may not claim the result.
        exported = outcome.counts.get(export.step_id)
        if exported is None:
            return []
        return [_eda_case(state, export, state.domain.eda_analysis, exported)]
    spec = state.domain.operational_spec
    candidates: list[MemoryCandidate] = []
    if spec is not None and spec.criteria and outcome.root_count is not None:
        candidates.append(_outcome_case(state, spec, outcome))
        candidates.extend(_recovery_cases(state, spec, outcome))
    return candidates


def _goal(state: PipelineState, spec: OperationalSpec | None) -> str:
    if spec is None:
        return state.domain.original_request or state.user_prompt
    return (
        state.domain.original_request
        or spec.interpreted_goal
        or spec.goal
        or state.user_prompt
    )


def _tags(state: PipelineState, spec: OperationalSpec | None) -> list[str]:
    tags = [state.site_id] if state.site_id else []
    if spec is not None and spec.organism_scope:
        tags.append(spec.organism_scope)
    return tags


def _params(criterion: Criterion) -> dict[str, str]:
    return {name: value.to_wire() for name, value in criterion.resolved_params.items()}


def _criteria_rows(spec: OperationalSpec) -> list[dict[str, object]]:
    return [
        {
            "text": criterion.text,
            "search_name": criterion.search_name,
            "role": criterion.role,
            "params": _params(criterion),
        }
        for criterion in spec.criteria
    ]


def _structure_line(spec: OperationalSpec) -> str:
    if spec.structure is None:
        return ""
    return render_structure(spec.structure.root, spec)


def _case_value(
    state: PipelineState,
    *,
    name: str,
    summary: str,
    content: dict[str, object],
    spec: OperationalSpec | None,
) -> MemoryCandidate:
    value = MemoryValue(
        kind="case",
        name=name[:_NAME_LIMIT],
        summary=summary[:_SUMMARY_LIMIT],
        tags=_tags(state, spec),
        site_id=state.site_id,
        content=content,
        source_conversation_id=state.conversation_id,
        created_at=datetime.now(UTC),
    )
    return value, f"case:{compute_content_hash(content)}"


def _outcome_case(
    state: PipelineState,
    spec: OperationalSpec,
    outcome: BuildOutcome,
) -> MemoryCandidate:
    goal = _goal(state, spec)
    structure = _structure_line(spec)
    content: dict[str, object] = {
        "case": "outcome",
        "goal": goal,
        "site": state.site_id,
        "structure": structure,
        "root_count": outcome.root_count,
        "criteria": _criteria_rows(spec),
    }
    return _case_value(
        state,
        name=goal or f"chat-{state.conversation_id.hex[:8]}",
        summary=f"{goal} reached {outcome.root_count} results through {structure}",
        content=content,
        spec=spec,
    )


def _recoveries(
    state: PipelineState,
    spec: OperationalSpec,
    outcome: BuildOutcome,
) -> list[tuple[ZeroResultStep, Criterion]]:
    """Each search that emptied a build of this thread and now has results,
    with the criterion that carries the params it has now."""
    filled = {
        node.search_name
        for node in outcome.node_results
        if node.status == "ok" and node.count
    }
    criterion_by_search = {c.search_name: c for c in spec.criteria if c.search_name}
    return [
        (entry, criterion_by_search[entry.search_name])
        for entry in state.domain.zero_result_history
        if entry.search_name in filled and entry.search_name in criterion_by_search
    ]


def _recovery_cases(
    state: PipelineState,
    spec: OperationalSpec,
    outcome: BuildOutcome,
) -> list[MemoryCandidate]:
    goal = _goal(state, spec)
    cases: list[MemoryCandidate] = []
    for entry, criterion in _recoveries(state, spec, outcome):
        params = _params(criterion)
        emptied_for = entry.criterion_text or criterion.text
        content: dict[str, object] = {
            "case": "recovery",
            "goal": goal,
            "site": state.site_id,
            "emptied_search": entry.search_name,
            "emptied_criterion": emptied_for,
            "fixed_params": params,
            "root_count": outcome.root_count,
        }
        rendered = ", ".join(f"{name}={value}" for name, value in params.items())
        cases.append(
            _case_value(
                state,
                name=f"{entry.search_name} returned zero for {goal}",
                summary=(
                    f"{entry.search_name} returned zero for {emptied_for}; "
                    f"{rendered} returns results"
                ),
                content=content,
                spec=spec,
            ),
        )
    return cases


def _volcano_cut(export: EdaExport) -> str:
    """The cut the export applied, as a phrase, or an empty string."""
    if export.effect_size_threshold is None or export.significance_threshold is None:
        return ""
    return (
        f" at |effect| >= {export.effect_size_threshold}, "
        f"p <= {export.significance_threshold}"
    )


def _eda_case(
    state: PipelineState,
    export: EdaExport,
    facts: EdaAnalysisFacts | None,
    exported_count: int,
) -> MemoryCandidate:
    """The case an EDA export leaves: the study and cut that reached a count.

    The count is the exported step's own, which is what the cut selected; the
    strategy's root can hold a different number.
    """
    goal = _goal(state, None)
    study = facts.study_display_name if facts is not None else ""
    analysis = facts.display_name if facts is not None else ""
    filters = list(facts.filter_summaries) if facts is not None else []
    content: dict[str, object] = {
        "case": "eda-export",
        "goal": goal,
        "site": state.site_id,
        "study": study,
        "dataset": export.dataset_id,
        "analysis": analysis,
        "filters": filters,
        "search_name": export.search_name,
        "is_compute_backed": export.is_compute_backed,
        "effect_size_threshold": export.effect_size_threshold,
        "significance_threshold": export.significance_threshold,
        "effect_direction": export.effect_direction,
        "exported_count": exported_count,
    }
    return _case_value(
        state,
        name=goal or f"{study} export",
        summary=(
            f"{goal} reached {exported_count} results from {study}"
            f"{_volcano_cut(export)}"
        ),
        content=content,
        spec=None,
    )
