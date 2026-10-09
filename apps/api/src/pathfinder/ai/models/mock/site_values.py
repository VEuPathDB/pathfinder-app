"""The values an arc binds on one site, read from that site's seed strategies."""

from __future__ import annotations

from collections import Counter
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.domain.strategy.organism import extract_output_organisms
from veupathdb.domain.strategy.tree import leaves
from veupathdb.wdk import load_sites_config

from pathfinder.platform.config import get_settings
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site

ParamValues = dict[str, str | list[str] | None]

_DECODED: TypeAdapter[str | list[str]] = TypeAdapter(str | list[str])
# Each search the seeds run, and the parameter WDK marks as its organism, as
# the site's catalog answered it; null where the search marks none. It is
# written by ``python -m pathfinder.devtools.seeds marks``.
MARKS_FILE = Path(__file__).with_name("organism_params.json")
_MARKS: TypeAdapter[dict[str, dict[str, str | None]]] = TypeAdapter(
    dict[str, dict[str, str | None]]
)


class SeedLeaf(BaseModel):
    """One search a seed runs on the site organism, with the values it holds."""

    model_config = ConfigDict(frozen=True)

    search_name: str
    values: ParamValues


class SiteControls(BaseModel):
    """A seed's curated positive and negative gene ids."""

    model_config = ConfigDict(frozen=True)

    name: str
    positive_ids: list[str]
    negative_ids: list[str]


class SiteValues(BaseModel):
    """What the arcs of one site bind: its organism, its searches, its controls."""

    model_config = ConfigDict(frozen=True)

    site_id: str
    organism: str
    leaves: tuple[SeedLeaf, ...]
    controls: SiteControls
    portal_organisms: tuple[str, ...]
    is_portal: bool

    @classmethod
    def for_site(cls, site_id: str) -> SiteValues:
        return _values(site_id)

    def leaf(self, search_name: str) -> SeedLeaf | None:
        return next((s for s in self.leaves if s.search_name == search_name), None)


@cache
def recorded_marks_by_site() -> dict[str, dict[str, str | None]]:
    """Each seed site, and the marks of the searches its seeds run."""
    return _MARKS.validate_json(MARKS_FILE.read_bytes())


def recorded_marks(site_id: str) -> dict[str, str | None]:
    """Each search the site's seeds run, and its marked organism parameter."""
    return recorded_marks_by_site()[site_id]


def _marked(site_id: str) -> dict[str, str]:
    return {
        search: param
        for search, param in recorded_marks(site_id).items()
        if param is not None
    }


def _nodes(site_id: str) -> list[StrategyStepNode]:
    return [
        leaf
        for seed in get_seeds_for_site(site_id)
        for leaf in leaves(seed.step_node())
    ]


def _organisms_ranked(site_id: str) -> list[str]:
    """The organisms the site's seed searches run on, the most run first."""
    marks = _marked(site_id)
    counted = Counter(
        organism
        for node in _nodes(site_id)
        for organism in sorted(extract_output_organisms(node, marks) or ())
    )
    return [organism for organism, _ in counted.most_common()]


def _organism_of(site_id: str) -> str | None:
    """The organism the most seed searches of the site run on."""
    return next(iter(_organisms_ranked(site_id)), None)


def _decoded(node: StrategyStepNode, organism: str, organism_param: str) -> ParamValues:
    values: ParamValues = {}
    for name, value in node.parameters.items():
        if name == organism_param:
            values[name] = [organism]
            continue
        try:
            values[name] = _DECODED.validate_python(value.to_decoded())
        except ValidationError:
            continue
    return values


def _seed_leaves(site_id: str, organism: str) -> tuple[SeedLeaf, ...]:
    """The first seed leaf of each search that runs on the site organism."""
    marks = _marked(site_id)
    found: dict[str, SeedLeaf] = {}
    for node in _nodes(site_id):
        if node.search_name in found:
            continue
        if extract_output_organisms(node, marks) != {organism}:
            continue
        found[node.search_name] = SeedLeaf(
            search_name=node.search_name,
            values=_decoded(node, organism, marks[node.search_name]),
        )
    return tuple(found.values())


def _portal_organisms(site_id: str) -> tuple[str, ...]:
    """The organisms the portal's seeds run on, the most run first, without the
    site's own. The portal holds each of them."""
    sites = load_sites_config(get_settings().veupathdb_sites_config).sites
    portal = next(site for site, config in sites.items() if config.is_portal)
    own = _organism_of(site_id)
    return tuple(o for o in _organisms_ranked(portal) if o != own)


@cache
def _values(site_id: str) -> SiteValues:
    organism = _organism_of(site_id)
    if organism is None:
        msg = f"No seed of {site_id} names an organism"
        raise LookupError(msg)
    control_set = get_seeds_for_site(site_id)[0].control_set
    return SiteValues(
        site_id=site_id,
        organism=organism,
        leaves=_seed_leaves(site_id, organism),
        controls=SiteControls(
            name=control_set.name,
            positive_ids=control_set.positive_ids,
            negative_ids=control_set.negative_ids,
        ),
        portal_organisms=_portal_organisms(site_id),
        is_portal=load_sites_config(get_settings().veupathdb_sites_config)
        .sites[site_id]
        .is_portal,
    )
