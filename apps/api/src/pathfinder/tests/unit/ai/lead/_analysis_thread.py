"""A thread whose strategy holds DESeq2 exports of the 24 h time point.

The export runs the production ``create_eda_step`` over the thread's own
state; the analysis read and the commit are stand-ins, and the commit applies
the operations to the thread's graph as the real one does.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp
from veupathdb.eda import EdaAnalysisDetail
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone.eda_step import EdaStepCreated
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.services.eda.export import eda_step_request, exported_analysis
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_step_doubles import (
    DE_DATASET,
    binding_of,
    de_analysis,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    joined,
    leaf,
    session_holding,
)

WAITING = "c_24h_vs_36_up"
WAITING_TEXT = "genes significantly higher at 24 h than at 36 h post blood meal"
REQUEST = (
    "Find genes significantly upregulated at 24 h post blood meal versus 18 h and 36 h"
)


def deseq(reference: str) -> EdaAnalysisDetail:
    """The analysis's one DESeq2 comparison: 24h against ``reference``.

    Each compute replaces the computation the analysis holds, so every
    comparison is read from the same analysis id.
    """
    return de_analysis(
        filters=[], with_computation=True, group_a=(reference,), group_b=("24h",)
    )


def document(reference: str, significance: float) -> StringValue:
    """The analysis document an export of this comparison writes on its step."""
    request = eda_step_request(
        deseq(reference),
        dataset_id=DE_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=significance,
        effect_direction="upOnly",
    )
    return StringValue(value=request.eda_analysis_spec)


def bare_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """A thread with no spec and no step, asked the measured question."""
    thread = DisagreementThread(
        monkeypatch, spec=OperationalSpec(), session=session_holding()
    )
    thread.deps.state.domain.operational_spec = None
    thread.deps.state.user_prompt = REQUEST
    return thread


async def export(
    thread: DisagreementThread,
    *,
    reference: str,
    criterion_id: str | None = None,
    combine_with_root: CombineOp | None = None,
) -> EdaStepCreated:
    """Export the genes higher at 24h than at ``reference``, at p 0.05."""
    detail = deseq(reference)

    async def _bound(_ctx: object) -> ConversationAnalysisView:
        return binding_of(detail)

    async def _read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        assert analysis_id == detail.analysis_id
        return detail

    async def _commit(**kwargs: Any) -> CommitResult:
        for op in kwargs["ops"]:
            apply_operation(thread.graph, op)
        thread.graph.note_analysis_kinds(kwargs["deps"].analysis_kinds)
        thread.committed.extend(kwargs["ops"])
        return CommitResult(description="exported")

    patch = thread.monkeypatch.setattr
    patch(eda_step, "bound_analysis", _bound)
    patch(eda_step, "read_analysis", _read)
    patch(eda_step, "apply_operations_and_commit", _commit)
    answer = await eda_step.create_eda_step(
        run_context_for(thread.deps, f"t_export_{reference}"),
        criterion_id=criterion_id,
        combine_with_root=combine_with_root,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upOnly",
        caption=f"Genes higher in 24h than in {reference}",
    )
    thread.assert_invariants()
    return returned(answer, EdaStepCreated)


def with_the_waiting_comparison(
    kept: str,
) -> Callable[[OperationalSpec], OperationalSpec]:
    """FRAME keeps the export and records the 36 h comparison waiting beside it."""

    def draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria.append(
            Criterion(id=WAITING, text=WAITING_TEXT, needs_analysis_on=DE_DATASET)
        )
        found.structure = SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf(kept), leaf(WAITING))
        )
        return found

    return draft


def bindings(thread: DisagreementThread) -> dict[str, AnalysisBinding]:
    """Every compute step the graph holds, read back from its own document."""
    found: dict[str, AnalysisBinding] = {}
    for step_id, step in thread.graph.steps.items():
        if step.search_name != COMPUTE_QUERY:
            continue
        binding = exported_analysis(
            thread.graph.analysis_kind_of(step_id), step.parameters
        )
        assert binding is not None
        found[step_id] = binding
    return found
