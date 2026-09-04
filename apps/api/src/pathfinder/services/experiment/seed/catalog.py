"""The seed catalog: the sites that ship seeds and the JSON behind each one."""

from importlib.resources import files
from importlib.resources.abc import Traversable

from pydantic import TypeAdapter

from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.experiment.seed.types import SeedDef

SEED_DATABASES: list[str] = [
    "plasmodb",
    "toxodb",
    "cryptodb",
    "piroplasmadb",
    "tritrypdb",
    "fungidb",
    "vectorbase",
    "giardiadb",
    "amoebadb",
    "microsporidiadb",
    "hostdb",
    "veupathdb",
    "orthomcl",
]

SEEDS_DIR: Traversable = files("pathfinder") / "data" / "seeds"

_SEED_LIST = TypeAdapter(list[SeedDef])


def get_seeds_for_site(site_id: str) -> list[SeedDef]:
    """Return the seed definitions of one site."""
    if site_id not in SEED_DATABASES:
        raise NotFoundError(
            code=ErrorCode.SITE_NOT_FOUND,
            title="Site not found",
            detail=f"No seed definitions for site: {site_id}",
        )
    return _SEED_LIST.validate_json((SEEDS_DIR / f"{site_id}.json").read_bytes())


def get_all_seeds() -> list[SeedDef]:
    """Return the seed definitions of every site, in catalog order."""
    return [seed for site in SEED_DATABASES for seed in get_seeds_for_site(site)]
