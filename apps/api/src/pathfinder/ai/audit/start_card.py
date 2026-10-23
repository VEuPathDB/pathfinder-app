"""The card a parked audit start asks on, drawn from the api's own replan of the request."""

from __future__ import annotations

from typing import Any

import httpx
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.tool_summary import summary_chunks
from pydantic import BaseModel, ConfigDict
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolResults, ToolDenied
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_site

from pathfinder.ai.audit.run_tools import NOTHING_STARTED, START_TOOL, planner_refusal
from pathfinder.ai.capabilities.site_reads import site_words
from pathfinder.domain.audit.planning import (
    START_LABEL,
    AuditStartCard,
    PlanAsk,
    PlanRequest,
    start_card,
)
from pathfinder.services.audit.planning import propose_scope
from pathfinder.services.site_errors import site_status

_SIGN_IN_REFUSALS = frozenset({401, 403})


class _ParkedStart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request: PlanAsk


def audit_start_event(card: AuditStartCard) -> DataChunk:
    return DataChunk(
        type="data-audit-start",
        id=card.tool_call_id,
        data=card.model_dump(by_alias=True, mode="json"),
    )


def _declined(tool_call_id: str, reason: str, writer: Any) -> tuple[str, ToolDenied]:
    for chunk in summary_chunks(tool_call_id, reason, status="warn"):
        emit_chunk(writer, chunk)
    return tool_call_id, ToolDenied(reason)


async def _card(
    call: ToolCallPart, writer: Any, site_id: str
) -> tuple[str, ToolDenied] | None:
    parked = _ParkedStart.model_validate(call.args_as_dict())
    try:
        fresh = await propose_scope(PlanRequest.on_site(parked.request, site_id))
    except (VEuPathDBError, httpx.HTTPError, TimeoutError, ConnectionError) as exc:
        if site_status(exc) in _SIGN_IN_REFUSALS:
            raise
        said = (
            f"{get_site(site_id).name} did not answer the planner's reads "
            f"({site_words(exc)}). {NOTHING_STARTED}"
        )
        return _declined(call.tool_call_id, said, writer)
    if fresh.scope is None:
        return _declined(call.tool_call_id, planner_refusal(fresh), writer)
    for chunk in summary_chunks(call.tool_call_id, START_LABEL):
        emit_chunk(writer, chunk)
    emit_chunk(
        writer, audit_start_event(start_card(fresh, tool_call_id=call.tool_call_id))
    )
    return None


async def ask_about_the_audits(
    requests: DeferredToolRequests, writer: Any, *, site_id: str
) -> DeferredToolResults | None:
    declined = [
        found
        for call in requests.approvals
        if call.tool_name == START_TOOL
        and (found := await _card(call, writer, site_id)) is not None
    ]
    return DeferredToolResults(approvals=dict(declined)) if declined else None
