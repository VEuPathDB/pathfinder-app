"""A check reads the upload each step runs on before it runs, so the ledger it
reads grounds a data-type requirement on the upload's type."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ToolCallPart
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintStatus
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import bound_uploads
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests._support.user_dataset_doubles import UPLOAD_DATASET
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
    requirement,
    tool_script_model,
)

pytestmark = pytest.mark.usefixtures("collector")

# The recorded DESeq flow on plasmodb: one step of 39 genes on the upload.
_STEP = "step_cb47c568"
_DIGEST: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": "The strategy returns 39 genes from the uploaded study.",
        "reason": "The DESeq comparison and cutoffs are confirmed.",
        "success": True,
    },
}


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("graph-1", "DESeq", "plasmodb")
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id=_STEP, kind=StepKind.SEARCH, search_name="GenesByDESeqUserDataset"
        ),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP: 441127973},
        step_counts={_STEP: 39},
        wdk_strategy_id=330857143,
    )
    return session


def _deseq_state() -> Any:
    state = pipeline_state(
        user_prompt=(
            "On my uploaded RNA-Seq dataset 'pathfinder-uat-deseq', find the genes "
            "differentially expressed between the treated and the control samples "
            "with DESeq2, at the default cutoffs."
        )
    )
    state.domain.operational_spec = OperationalSpec(
        goal="DESeq2 on my upload",
        criteria=[
            Criterion(
                id=_STEP,
                text="Genes differentially expressed in pathfinder-uat-deseq.",
                search_name="GenesByDESeqUserDataset",
                analysis=AnalysisBinding(
                    dataset_id=UPLOAD_DATASET,
                    method="DESeq",
                    words="Genes that differ between Control and Treated",
                ),
            )
        ],
    )
    state.domain.requirements = [
        requirement(ConstraintKind.DATA_TYPE, "RNA-Seq dataset", "RNA-Seq")
    ]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[_STEP], wdk_strategy_id=330857143
    )
    return state


async def test_the_check_reads_the_uploads_type_before_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _uploads(site_id: str) -> list[OwnedUpload]:
        del site_id
        return [
            OwnedUpload(
                vdi_id="lhZ5ptRgo014J",
                name="pathfinder-uat-deseq",
                type_name="rnaseqrc",
            )
        ]

    monkeypatch.setattr(bound_uploads, "owned_uploads", _uploads)
    deps = lead_deps(_deseq_state(), strategy_session=_session())
    seen: list[DataMarks] = []

    def _answer(messages: list[ModelMessage]) -> ToolCallPart:
        del messages
        seen.append(deps.state.domain.data_marks)
        return final_result_part(_DIGEST)

    monkeypatch.setattr(
        sub_agent_tools, "get_mock_model", lambda: tool_script_model(_answer)
    )
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Return the digest the script names.",
    ):
        delta = await run_verification(
            deps=deps, parent_tool_call_id="lead_call_verify", reason="check"
        )

    assert isinstance(delta, VerificationDelta)
    [grounded] = derive_ledger(deps.state, None).constraints.grounded
    assert (seen, grounded.status, grounded.realized_value, delta.digest.success) == (
        [DataMarks(uploads={_STEP: "rnaseqrc"})],
        ConstraintStatus.GROUNDED,
        "rna-seq",
        True,
    )
