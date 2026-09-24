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
from veupathdb_mcp.gene_lookup import list_organisms

from pathfinder.assistants.site_help.mock import build_site_help_mock
from pathfinder.assistants.site_help.organisms import (
    MAX_SPECIES,
    OrganismSummary,
    organism_note,
    organism_summaries,
    organisms_of_genus,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.platform.model_keys import keyed_model
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import PhaseTierConfig, resolve_phase_tier_config

SITE_HELP_MODEL = "openai:gpt-5.6-luna"


class SiteHelpDeps(AssistantDeps):
    """The runtime's dependencies, plus the sources this turn resolved."""

    tool_sources: AbstractToolset[Any] | None = None


type SiteHelpAgent = Agent[SiteHelpDeps, str]

SITE_HELP_INSTRUCTIONS = (
    "You help researchers find their way around the VEuPathDB family of "
    "sites. Answer in plain markdown, briefly.\n\n"
    "Use `list_veupathdb_sites` to name the sites and what each one covers, "
    "and `describe_site` to report one site's record types, how many searches "
    "each of them offers, and the species it carries with their strain "
    "counts. A site with many species answers with the widest of them and "
    "says how many it left out; call it again with a genus to read that genus "
    "alone. Both tools read the live catalog: quote what they return and "
    "never invent a site, a record type, an organism or a count.\n\n"
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
    """What one site offers: its record types and the organisms it carries."""

    site_id: str
    display_name: str
    record_types: list[RecordTypeSummary]
    organisms: list[OrganismSummary]
    # The counts and the species are this genus's when one was applied.
    genus: str
    organism_count: int
    species_count: int
    organism_note: str = ""


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
    ctx: RunContext[SiteHelpDeps], site_id: str, genus: str = ""
) -> ToolReturn[SiteDetail]:
    """Report one site's record types, its search counts and its organisms.

    Call this when the user asks what a site holds, what they can search
    there, or which organisms or strains it covers. The organisms are the
    species of the site's own organism vocabulary, the ones with the most
    strains first, each with its strain count and up to three strain names.

    A site with many species answers with the first of them and says how many
    it left out. Name a genus to read that genus alone: the answer then names
    the genus it was narrowed to, and a genus the site does not carry comes
    back with the ones it does.

    Args:
        ctx: Agent run context.
        site_id: The id ``list_veupathdb_sites`` returns, such as ``plasmodb``.
        genus: One genus, such as ``Aspergillus``, or empty for every organism.
    """
    sites = {site.id: site for site in await list_sites()}
    site = sites.get(site_id)
    if site is None:
        msg = f"Unknown site {site_id!r}. The sites are: {sorted(sites)}."
        raise ModelRetry(msg)
    declared = await list_organisms(site_id)
    organisms = organisms_of_genus(declared, genus)
    if genus and not organisms:
        msg = (
            f"Unknown genus {genus!r} on {site_id}. The genera are: "
            f"{sorted({term.split()[0] for term in declared})}."
        )
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
    species = organism_summaries(organisms)
    return with_summary(
        SiteDetail(
            site_id=site.id,
            display_name=site.display_name,
            record_types=summaries,
            organisms=species[:MAX_SPECIES],
            genus=genus.strip(),
            organism_count=len(organisms),
            species_count=len(species),
            organism_note=organism_note(
                [one.species for one in species[MAX_SPECIES:]], genus.strip()
            ),
        ),
        f"{site.id}: {site.display_name}",
        ctx=ctx,
    )


def _tier() -> PhaseTierConfig | None:
    settings = get_settings()
    return resolve_phase_tier_config(
        SITE_HELP_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        SITE_HELP_ASSISTANT_ID,
    )


def turn_model_id() -> str:
    """The model this turn's role names: the user's pick, the tier, then the
    model this module names."""
    tier = _tier()
    return phase_overrides_ctx.get().models.get(SITE_HELP_ASSISTANT_ID) or (
        SITE_HELP_MODEL if tier is None else tier.model_id
    )


def turn_model() -> tuple[Model | str, ModelSettings | None]:
    """The model this turn runs under, and the settings that go with it.

    The mock provider swaps the whole model, so the turn makes no request.
    """
    if get_settings().pathfinder_chat_provider.strip().lower() == "mock":
        return build_site_help_mock(), None
    tier = _tier()
    model_id = turn_model_id()
    effort = phase_overrides_ctx.get().reasoning.get(SITE_HELP_ASSISTANT_ID) or (
        None if tier is None else tier.reasoning_effort
    )
    return model_id, build_model_settings(model_id, thinking=effort)


def build_site_help_agent() -> SiteHelpAgent:
    """A site-help agent for one turn, on the key that pays for its model."""
    model, model_settings = turn_model()
    return Agent(
        keyed_model(model),
        model_settings=model_settings,
        output_type=str,
        deps_type=SiteHelpDeps,
        instructions=SITE_HELP_INSTRUCTIONS,
        tools=[Tool(list_veupathdb_sites), Tool(describe_site)],
        toolsets=[turn_tool_sources],
        capabilities=agent_capabilities([]),
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
    "turn_model_id",
    "turn_tool_sources",
]
