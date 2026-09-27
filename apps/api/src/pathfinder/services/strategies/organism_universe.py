"""The genes an organism value set holds on a site, counted by the site's
organism search."""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.services.strategies.organism_params import organism_parameters
from pathfinder.services.strategies.wdk_counts import count_bound_criterion

# The WDK search that answers every gene of the organisms it selects.
ORGANISM_SEARCH = "GenesByTaxon"

# A site's gene counts change only with a release, so a count holds for the process.
_UNIVERSE_COUNTS: dict[tuple[str, str, tuple[str, ...]], int] = {}


async def universe_counts(
    site_id: str,
    record_type: str,
    organism_value_sets: Collection[tuple[str, ...]],
) -> dict[tuple[str, ...], int]:
    """The gene count of each sorted organism value set, one read per new set.

    A set whose count does not arrive is absent, and a site whose organism
    search marks no organism parameter counts nothing.
    """
    wanted = sorted(set(organism_value_sets))
    if not wanted:
        return {}
    marked = await organism_parameters(site_id, record_type, [ORGANISM_SEARCH])
    param = marked.get(ORGANISM_SEARCH)
    if param is None:
        return {}
    found: dict[tuple[str, ...], int] = {}
    for values in wanted:
        key = (site_id, record_type, values)
        if key not in _UNIVERSE_COUNTS:
            count = await count_bound_criterion(
                site_id,
                record_type,
                ORGANISM_SEARCH,
                {param: MultiPickValue(values=list(values))},
            )
            if count is None:
                continue
            _UNIVERSE_COUNTS[key] = count
        found[values] = _UNIVERSE_COUNTS[key]
    return found
