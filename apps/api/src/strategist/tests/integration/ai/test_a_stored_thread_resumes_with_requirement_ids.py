from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.graph.turn_state import PendingApproval
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, empty_checkpoint
from langgraph.checkpoint.serde.base import SerializerProtocol

from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.assistants.strategist_spec import (
    STRATEGIST_CHECKPOINT_TYPES,
    build_strategist_spec,
)
from strategist.domain.unmet_requirements import unmet_requirement_ids
from strategist.platform.config import get_settings
from strategist.tests._support.stored_domains import stored_domain_blob

_STORED = "domain-with-kind-value-keys"


class _StoredDomain:
    pass


class _WritesTheStoredDomain:
    def __init__(self, serde: SerializerProtocol) -> None:
        self._serde = serde

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        if type(obj) is _StoredDomain:
            return stored_domain_blob(_STORED)
        return self._serde.dumps_typed(obj)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return self._serde.loads_typed(data)


async def _resumed(channels: dict[str, object]) -> dict[str, Any]:
    config: RunnableConfig = {
        "configurable": {"thread_id": str(uuid4()), "checkpoint_ns": ""}
    }
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {**channels, "domain": _StoredDomain()}
    versions: ChannelVersions = dict.fromkeys(checkpoint["channel_values"], 1)
    checkpoint["channel_versions"] = dict(versions)
    async with lifespan_checkpointer(
        get_settings().database_url, checkpoint_types=STRATEGIST_CHECKPOINT_TYPES
    ) as saver:
        reading = saver.serde
        saver.serde = _WritesTheStoredDomain(reading)
        await saver.aput(config, checkpoint, {"source": "input", "step": -1}, versions)
        saver.serde = reading
        snapshot = await build_strategist_spec().build_graph(saver).aget_state(config)
    return snapshot.values


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_thread_an_earlier_build_stored_resumes_with_requirement_ids() -> None:
    domain = (await _resumed({}))["domain"]

    assert type(domain) is StrategyDomainState
    ids = {c.requested_value: c.id for c in domain.requirements}
    [retired] = domain.retired_requirements
    assert retired.lifecycle.model_dump() == {
        "state": "replaced",
        "by": ids["Plasmodium falciparum 3D7"],
    }


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_turn_an_earlier_build_parked_resumes_with_its_verdict_by_id() -> None:
    message = UUID(int=2)
    values = await _resumed(
        {
            "conversation_id": uuid4(),
            "user_id": uuid4(),
            "site_id": "plasmodb",
            "mode": "strategy",
            "user_prompt": "only Plasmodium falciparum 3D7",
            "user_message_id": message,
            "pending_approval": PendingApproval(
                phase="lead",
                tool_call_id="call_card",
                tool_name="consult_user",
                user_message_id=message,
            ),
        }
    )

    state = PipelineState(**values)
    [strain] = [
        c.id
        for c in state.domain.requirements
        if c.requested_value == "Plasmodium falciparum 3D7"
    ]
    verdict = state.turn_verdict
    assert verdict is not None
    assert (
        state.pending_approval is not None,
        unmet_requirement_ids(verdict.gaps),
        [c.requirement for c in verdict.review.checks],
        [c.id for c in state.turn_markers.requirements_added],
    ) == (True, [strain], [strain], [strain])
