"""A FRAME pass that stops on the user hands the Lead the card its recorded
questions become, each option stating the value it binds."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.graph.turn_state import ConsultOption

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OpenSlot
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


async def test_the_result_carries_the_card_that_asks_the_recorded_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each option on the card states the parameter and the value it binds."""

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(
                id="c1",
                text="gametocyte expression",
                search_name="GenesByRNASeqPercentile",
                param_display_names={"dataset": "RNA-Seq dataset"},
                open_params=[OpenSlot(criterion_id="c1", param_name="dataset")],
            )
        )
        return FrameResult(
            disposition="needs_user",
            summary="which dataset?",
            open_questions=[
                SlotQuestion(
                    question="Which gametocyte RNA-seq study?",
                    dimension=ConstraintKind.DATA_TYPE,
                    recommended_value="pfal3D7_Gametocyte",
                    criterion_id="c1",
                    param_name="dataset",
                    options=["pfal3D7_Gametocyte", "pfal3D7_Ookinete"],
                ),
            ],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    deps = lead_deps(pipeline_state(user_prompt="find gametocyte genes"))

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )

    assert isinstance(result, FrameResult)
    assert result.card_questions == [
        CardQuestion(
            id="q1",
            prompt="Which gametocyte RNA-seq study?",
            dimension=ConstraintKind.DATA_TYPE,
            options=[
                ConsultOption(
                    label="RNA-Seq dataset pfal3D7_Gametocyte", recommended=True
                ),
                ConsultOption(label="RNA-Seq dataset pfal3D7_Ookinete"),
            ],
        )
    ]
    [asked] = deps.state.domain.open_questions
    assert [o.label for o in asked.options] == [
        "RNA-Seq dataset pfal3D7_Gametocyte",
        "RNA-Seq dataset pfal3D7_Ookinete",
    ]


def test_the_frame_output_schema_asks_no_card_of_the_model() -> None:
    schema = FrameResult.model_json_schema(mode="validation")

    assert "cardQuestions" not in schema["properties"]
