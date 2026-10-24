from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from assistant_core.persistence.models import MonthlyUsage
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.usage import RequestUsage
from sqlalchemy import select

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.investigator import investigate
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests._support.audit import seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_OPENAI_KEY = ProviderKeyring(
    active={"openai": SecretStr("sk-proj-sentinel-0123456789WXYZ")}
)
_SPENT = RequestUsage(input_tokens=1000, output_tokens=200)


class _OpenAINamed(WrapperModel):
    @property
    def system(self) -> str:
        return "openai"

    @property
    def model_id(self) -> str:
        return f"{self.system}:{self.model_name}"


def _answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages
    (tool,) = info.output_tools
    call = ToolCallPart(
        tool_name=tool.name, args={"answer": "Nothing to judge.", "verdicts": []}
    )
    return ModelResponse(parts=[call], usage=_SPENT)


async def _investigated() -> UUID:
    owner = await seed_thread()
    deps = AuditDeps(
        site_id="plasmodb",
        user_id=owner.user_id,
        conversation_id=owner.conversation_id,
        origin="lead",
    )
    model = _OpenAINamed(FunctionModel(_answer, model_name="gpt-4o"))
    await investigate("is the model of EXA_0001 right", deps=deps, model=model)
    return owner.user_id


async def _rows(user_id: UUID) -> dict[PaidBy, tuple[int, Decimal]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(MonthlyUsage).where(MonthlyUsage.user_id == user_id)
        )
        return {
            row.paid_by: (row.total_tokens, row.total_cost_usd)
            for row in result.scalars()
        }


async def test_an_investigation_on_the_owners_key_is_charged_to_the_owner() -> None:
    with attach_keyring(_OPENAI_KEY):
        owner = await _investigated()

    assert await _rows(owner) == {PaidBy.USER: (1200, Decimal("0.004500"))}


async def test_an_investigation_with_no_key_is_charged_to_the_deployment() -> None:
    owner = await _investigated()

    assert await _rows(owner) == {PaidBy.DEPLOYMENT: (1200, Decimal("0.004500"))}
