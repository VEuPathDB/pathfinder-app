"""The auditor: the one agent of the audit assistant, its model, its tools and its limits."""

from __future__ import annotations

from typing import Any

from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.settings import build_model_settings
from langgraph.config import get_stream_writer
from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.capabilities import HandleDeferredToolCalls
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolResults, Tool
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import UsageLimits

from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES, build_check_toolset
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.instructions import AUDITOR_INSTRUCTIONS
from pathfinder.ai.audit.mock import build_audit_mock
from pathfinder.ai.audit.reply import AuditReply, HoldTheReply
from pathfinder.ai.audit.run_tools import READ_TOOL_NAMES, build_run_toolset
from pathfinder.ai.audit.start_card import ask_about_the_audits
from pathfinder.ai.audit.verdict_tool import record_gene_model_verdict
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.platform.model_catalog import DEFAULT_MODEL_ID
from pathfinder.platform.model_keys import keyed_model
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import (
    AUDITOR_ROLE,
    REVIEW_ROLE,
    deployment_role_config,
    role_model,
)

AUDITOR_MODEL = DEFAULT_MODEL_ID
AUDITOR_LIMITS = UsageLimits(request_limit=40, tool_calls_limit=40)

type AuditorAgent = Agent[AuditDeps, AuditReply | DeferredToolRequests]


def audit_compile_time_models() -> dict[str, str]:
    return {AUDITOR_ROLE: AUDITOR_MODEL, REVIEW_ROLE: AUDITOR_MODEL}


def auditor_model_id() -> str:
    return role_model(AUDIT_ASSISTANT_ID, AUDITOR_ROLE, compile_time=AUDITOR_MODEL)


def _model() -> tuple[Model | str, ModelSettings | None]:
    if get_settings().pathfinder_chat_provider.strip().lower() == "mock":
        return build_audit_mock(), None
    model_id = auditor_model_id()
    config = deployment_role_config(AUDIT_ASSISTANT_ID, AUDITOR_ROLE)
    effort = None if config is None else config.reasoning_effort
    return (
        maybe_wrap_model(keyed_model(model_id), AUDITOR_ROLE),
        build_model_settings(model_id, thinking=effort),
    )


def turn_tool_sources(ctx: RunContext[AuditDeps]) -> AbstractToolset[Any] | None:
    return ctx.deps.tool_sources


async def ask_about_the_audits_handler(
    ctx: RunContext[AuditDeps], requests: DeferredToolRequests
) -> DeferredToolResults | None:
    return await ask_about_the_audits(
        requests, get_stream_writer(), site_id=ctx.deps.site_id
    )


def build_auditor_agent() -> AuditorAgent:
    model, settings = _model()
    return Agent(
        model,
        model_settings=settings,
        output_type=[AuditReply, DeferredToolRequests],
        deps_type=AuditDeps,
        instructions=AUDITOR_INSTRUCTIONS,
        tools=[Tool(record_gene_model_verdict, max_retries=3)],
        toolsets=[build_run_toolset(), build_check_toolset(), turn_tool_sources],
        capabilities=agent_capabilities(
            [
                SiteReadFailures[AuditDeps](reads=CHECK_TOOL_NAMES | READ_TOOL_NAMES),
                HandleDeferredToolCalls[AuditDeps](
                    handler=ask_about_the_audits_handler
                ),
                HoldTheReply(),
            ]
        ),
        retries=3,
        name=AUDITOR_ROLE,
        defer_model_check=True,
    )
