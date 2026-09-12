"""The site-help agent: two local catalog tools, plus what the turn resolved."""

from __future__ import annotations

from typing import Any

from assistant_core.graph.runtime import AssistantDeps
from assistant_core.graph.tool_summary import with_summary
from assistant_core.models.settings import build_model_settings
from assistant_core.platform.context import phase_overrides_ctx
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import Agent, ModelRetry, Tool
from pydantic_ai.messages import ToolReturn
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import RunContext
from pydantic_ai.toolsets import AbstractToolset
from veupathdb_mcp.catalog import get_raw_searches, get_record_types, list_sites

from pathfinder.assistants.site_help.mock import build_site_help_mock
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.platform.tiers import resolve_phase_tier_config

SITE_HELP_MODEL = "openai:gpt-5.6-luna"


class SiteHelpDeps(AssistantDeps):
    """The runtime's dependencies, plus the sources this turn resolved."""

    tool_sources: AbstractToolset[Any] | None = None


type SiteHelpAgent = Agent[SiteHelpDeps, str]

SITE_HELP_INSTRUCTIONS = (
    "You help researchers find their way around the VEuPathDB family of "
    "sites. Answer in plain markdown, briefly.\n\n"
    "Use `list_veupathdb_sites` to name the sites and what each one covers, "
    "and `describe_site` to report one site's record types and how many "
    "searches each of them offers. Both tools read the live catalog: quote "
    "what they return and never invent a site, a record type or a count.\n\n"
    "Where this deployment reaches the VEuPathDB WDK server, three more tools "
    "answer: `wdk_list_record_types` and `wdk_search_for_searches` read one "
    "site's catalog, and `wdk_run_control_tests_on_search` measures a search "
    "against known genes. Call the one the question needs. This deployment "
    "asks the user to approve a call that writes, so never ask for consent in "
    "prose: make the call and report what comes back, including a refusal. A "
    "tool you cannot see is one this deployment does not offer: say so rather "
    "than describing what it would return.\n\n"
    "You do not build strategies for the user and you change nothing they "
    "saved. When a request needs that, say so and point at the site the work "
    "belongs on."
)


def turn_tool_sources(ctx: RunContext[SiteHelpDeps]) -> AbstractToolset[Any] | None:
    """The servers this turn resolved, as the tools of this run."""
    return ctx.deps.tool_sources


class SiteSummary(CamelModel):
    """One VEuPathDB site, as the catalog registers it."""

    site_id: str
    display_name: str
    url: str


class RecordTypeSummary(CamelModel):
    """One record type a site serves, with how many searches reach it."""

    name: str
    display_name: str
    search_count: int


class SiteDetail(CamelModel):
    """What one site offers, by record type."""

    site_id: str
    display_name: str
    record_types: list[RecordTypeSummary]


async def list_veupathdb_sites(
    ctx: RunContext[SiteHelpDeps],
) -> ToolReturn[list[SiteSummary]]:
    """List every VEuPathDB site this deployment can reach.

    Call this when the user asks which sites exist, which one covers an
    organism, or where a kind of data lives.
    """
    summaries = [
        SiteSummary(site_id=site.id, display_name=site.display_name, url=site.base_url)
        for site in await list_sites()
    ]
    return with_summary(summaries, f"{len(summaries)} sites", ctx=ctx)


async def describe_site(
    ctx: RunContext[SiteHelpDeps], site_id: str
) -> ToolReturn[SiteDetail]:
    """Report one site's record types and the search count of each.

    ``site_id`` is the id ``list_veupathdb_sites`` returns, such as
    ``plasmodb``. Call this when the user asks what a site holds or what
    they can search there.
    """
    sites = {site.id: site for site in await list_sites()}
    site = sites.get(site_id)
    if site is None:
        msg = f"Unknown site {site_id!r}. The sites are: {sorted(sites)}."
        raise ModelRetry(msg)
    record_types = await get_record_types(site_id)
    summaries = [
        RecordTypeSummary(
            name=record_type.name,
            display_name=record_type.display_name,
            search_count=len(await get_raw_searches(site_id, record_type.name)),
        )
        for record_type in record_types
    ]
    return with_summary(
        SiteDetail(
            site_id=site.id,
            display_name=site.display_name,
            record_types=summaries,
        ),
        f"{site.id}: {site.display_name}",
        ctx=ctx,
    )


def turn_model() -> tuple[Model | str, ModelSettings | None]:
    """The model this turn runs under, and the settings that go with it.

    The mock provider swaps the whole model, so the turn makes no request.
    Otherwise the user's pick for this role wins over the configured tier,
    which wins over the model this module names.
    """
    settings = get_settings()
    if settings.pathfinder_chat_provider.strip().lower() == "mock":
        return build_site_help_mock(), None
    tier = resolve_phase_tier_config(
        SITE_HELP_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        SITE_HELP_ASSISTANT_ID,
    )
    overrides = phase_overrides_ctx.get()
    model_id = overrides.models.get(SITE_HELP_ASSISTANT_ID) or (
        SITE_HELP_MODEL if tier is None else tier.model_id
    )
    effort = overrides.reasoning.get(SITE_HELP_ASSISTANT_ID) or (
        None if tier is None else tier.reasoning_effort
    )
    return model_id, build_model_settings(model_id, thinking=effort)


def build_site_help_agent() -> SiteHelpAgent:
    """A site-help agent for one turn."""
    model, model_settings = turn_model()
    return Agent(
        model,
        model_settings=model_settings,
        output_type=str,
        deps_type=SiteHelpDeps,
        instructions=SITE_HELP_INSTRUCTIONS,
        tools=[Tool(list_veupathdb_sites), Tool(describe_site)],
        toolsets=[turn_tool_sources],
        retries=2,
        description="Points users around the VEuPathDB sites",
        name="site_help",
        defer_model_check=True,
    )


__all__ = [
    "SITE_HELP_INSTRUCTIONS",
    "SITE_HELP_MODEL",
    "RecordTypeSummary",
    "SiteDetail",
    "SiteHelpAgent",
    "SiteHelpDeps",
    "SiteSummary",
    "build_site_help_agent",
    "describe_site",
    "list_veupathdb_sites",
    "turn_model",
    "turn_tool_sources",
]
