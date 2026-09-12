"""The briefing a turn opens with: what moved since the Lead last answered.

The Lead's other pinned renders describe the thread as it stands now. This one
describes the change, so an edit made in the graph editor, a task the worker
finished and an analysis mutated in the EDA tab all reach the turn that follows
them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, walk

from pathfinder.domain.strategy.ast_diff import (
    StepChange,
    StrategyAstDiff,
    diff_strategy_asts,
)
from pathfinder.domain.strategy.constraint_grounding import ground_constraints
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
)
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.services.conversations.thread_activity import (
    AnalysisDrift,
    FinishedTask,
    ThreadActivity,
)

__all__ = [
    "MAX_BRIEFING_CHARS",
    "MAX_BRIEFING_LINES",
    "ConstraintShift",
    "TurnBriefing",
    "compose_turn_briefing",
]

MAX_BRIEFING_LINES = 8
# About two hundred tokens of prose, whatever the values on the steps are.
MAX_BRIEFING_CHARS = 800
_HEADING = "## Since your last turn"
_CLOSING = (
    "These are facts about the thread, not a request. Call "
    "get_live_strategy_state before you quote a count."
)
_MAX_PARAMS_PER_STEP = 2
_MAX_VALUE_CHARS = 24
_MAX_LABEL_CHARS = 40


class ConstraintShift(BaseModel):
    """One requirement whose grounding changed with the strategy."""

    model_config = ConfigDict(frozen=True)

    label: str
    before: ConstraintStatus
    after: ConstraintStatus


class TurnBriefing(BaseModel):
    """Everything that moved between the last answer and this turn."""

    model_config = ConfigDict(frozen=True)

    strategy: StrategyAstDiff = Field(default_factory=StrategyAstDiff)
    tasks: list[FinishedTask] = Field(default_factory=list)
    analysis: AnalysisDrift | None = None
    constraints: list[ConstraintShift] = Field(default_factory=list)

    @property
    def moved(self) -> bool:
        return bool(
            self.strategy.moved or self.tasks or self.analysis or self.constraints
        )

    def render(self) -> str:
        """The pinned text, or ``""`` when the thread did not move."""
        lines = self._lines()
        if not lines:
            return ""
        shown = _within_budget(lines)
        elided = len(lines) - len(shown)
        if elided:
            shown.append(f"- and {elided} more changes")
        return "\n".join([_HEADING, *shown, _CLOSING])

    def _lines(self) -> list[str]:
        return [
            *(_step_line(change) for change in self.strategy.changed),
            *(
                f"- {step.label} ({step.step_id}): added"
                for step in self.strategy.added
            ),
            *(
                f"- {step.label} ({step.step_id}): removed"
                for step in self.strategy.removed
            ),
            *(_task_line(task) for task in self.tasks),
            *([_analysis_line(self.analysis)] if self.analysis is not None else []),
            *(
                f'- "{shift.label}": {shift.before} -> {shift.after}'
                for shift in self.constraints
            ),
        ]


def _within_budget(lines: list[str]) -> list[str]:
    """The lines that fit the budget. The first one always fits."""
    kept: list[str] = []
    spent = 0
    for line in lines[:MAX_BRIEFING_LINES]:
        if kept and spent + len(line) > MAX_BRIEFING_CHARS:
            break
        kept.append(line)
        spent += len(line)
    return kept


def _clipped(value: str | None, limit: int = _MAX_VALUE_CHARS) -> str:
    """A value short enough for one line. A whole gene list is not one."""
    if value is None:
        return "(unset)"
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _step_line(change: StepChange) -> str:
    parts: list[str] = []
    if change.search_after is not None:
        parts.append(f"search {change.search_before} -> {change.search_after}")
    parts.extend(
        f"{param.name} {_clipped(param.before)} -> {_clipped(param.after)}"
        for param in change.params[:_MAX_PARAMS_PER_STEP]
    )
    dropped = len(change.params) - _MAX_PARAMS_PER_STEP
    if dropped > 0:
        parts.append(f"+{dropped} more params")
    label = _clipped(change.label, _MAX_LABEL_CHARS)
    return f"- {label} ({change.step_id}): {', '.join(parts)}"


def _task_line(task: FinishedTask) -> str:
    return f"- {task.tool_name} {'failed' if task.failed else 'finished'}"


def _analysis_line(drift: AnalysisDrift) -> str:
    return (
        f"- the open analysis ({drift.dataset_id}) is "
        f"{drift.revisions_ahead} revisions ahead of the card in this thread"
    )


def compose_turn_briefing(
    activity: ThreadActivity,
    *,
    requirements: list[Constraint],
) -> TurnBriefing:
    """Turn one thread's activity into the briefing the Lead reads."""
    return TurnBriefing(
        strategy=diff_strategy_asts(activity.strategy_before, activity.strategy_after),
        tasks=list(activity.finished_tasks),
        analysis=activity.analysis,
        constraints=_regrounded(
            requirements,
            before=activity.strategy_before,
            after=activity.strategy_after,
        ),
    )


def _regrounded(
    requirements: list[Constraint],
    *,
    before: StrategyAst | None,
    after: StrategyAst | None,
) -> list[ConstraintShift]:
    """Requirements whose grounding differs between the two states."""
    if not requirements or before is None or after is None:
        return []
    was = _statuses(requirements, before)
    now = _statuses(requirements, after)
    return [
        ConstraintShift(label=requirement.label, before=was[index], after=now[index])
        for index, requirement in enumerate(requirements)
        if was[index] != now[index]
    ]


def _statuses(
    requirements: list[Constraint],
    ast: StrategyAst,
) -> list[ConstraintStatus]:
    nodes = list(walk(ast.root))
    for detached in ast.detached_roots:
        nodes.extend(walk(detached))
    values = _param_values(nodes)
    spec = spec_from_ast(ast, goal="")
    return [
        grounded.status
        for grounded in ground_constraints(
            requirements,
            search_names=[node.search_name for node in nodes],
            param_names=values.keys(),
            param_values=values,
            structure=spec.structure,
            criteria=spec.criteria,
        )
    ]


def _param_values(nodes: list[StrategyStepNode]) -> dict[str, str]:
    return {
        name: to_wire(value)
        for node in nodes
        for name, value in node.parameters.items()
    }
