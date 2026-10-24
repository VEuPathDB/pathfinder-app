from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import AbstractModel, Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.audit import investigator
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.sub_agent_tools import SubAgentRunUsage
from pathfinder.ai.tools.standalone.gene_model_investigation import (
    NO_REQUEST_MODEL,
    investigate_gene_models,
    request_model,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


class _Spoken(AbstractModel):
    @property
    def model_name(self) -> str:
        return "spoken"

    @property
    def system(self) -> str:
        return "voice"


def test_a_request_model_investigates() -> None:
    model = TestModel()

    assert request_model(model) is model


def test_a_model_that_answers_no_request_is_refused() -> None:
    with pytest.raises(CallRefused) as refused:
        request_model(_Spoken())

    assert str(refused.value) == NO_REQUEST_MODEL


def _talks(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages, info
    return ModelResponse(parts=[TextPart("I think the model is fine.")])


async def test_an_investigation_that_fails_is_charged_once_and_counted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    charged: list[int] = []

    async def charge(
        user_id: UUID, usage: RunUsage, model: Model, *, model_id: str
    ) -> None:
        del user_id, model, model_id
        charged.append(usage.requests)

    monkeypatch.setattr(investigator, "charge_run", charge)
    recorded: list[SubAgentRunUsage] = []
    deps = lead_deps(pipeline_state(user_prompt="q"), record_usage=recorded.append)
    agent_deps = agent_deps_for(deps, call_id="call_investigate")
    ctx = replace(
        run_context_for(agent_deps, "call_investigate"), model=FunctionModel(_talks)
    )

    with pytest.raises(UnexpectedModelBehavior):
        await investigate_gene_models(ctx, "is EXA_0001 right", origin="lead")

    assert charged == [4]
    assert [(r.usage.requests, r.billed) for r in recorded] == [(4, True)]
