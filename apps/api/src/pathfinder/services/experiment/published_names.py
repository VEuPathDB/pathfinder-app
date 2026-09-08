"""What WDK calls a search and each of its parameters."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.search import SearchContext
from veupathdb.errors import VEuPathDBError
from veupathdb.logging import get_logger
from veupathdb_mcp.catalog.param_resolution import get_search_parameters

from pathfinder.platform.errors import AppError

logger = get_logger(__name__)


class PublishedNames(CamelModel):
    """The display names WDK publishes for a search and its parameters."""

    label: str = ""
    parameter_labels: dict[str, str] = Field(default_factory=dict)


async def published_names(
    site_id: str,
    record_type: str,
    search_name: str,
) -> PublishedNames:
    """Read those names from the site catalog. Empty when WDK refuses the read."""
    try:
        resolved = await get_search_parameters(
            SearchContext(site_id, record_type, search_name)
        )
    except (VEuPathDBError, AppError, OSError) as exc:
        logger.warning(
            "The published names of a search could not be read",
            search_name=search_name,
            error=str(exc),
        )
        return PublishedNames()
    # The catalog answers the url segment when a search publishes no display
    # name, and a url segment is not a name a reader knows.
    published = "" if resolved.display_name == search_name else resolved.display_name
    return PublishedNames(
        label=published,
        parameter_labels={
            info.name: info.display_name or info.name for info in resolved.parameters
        },
    )
