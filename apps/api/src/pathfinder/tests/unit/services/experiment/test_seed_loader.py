"""Shape and count invariants of the JSON seed catalog."""

import pytest
from pydantic import ValidationError

from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    SEEDS_DIR,
    get_all_seeds,
    get_seeds_for_site,
)
from pathfinder.services.experiment.seed.runner import _coerce_step_tree_params
from pathfinder.services.experiment.seed.types import SeedDef

EXPECTED_COUNTS: dict[str, int] = {
    "plasmodb": 6,
    "toxodb": 6,
    "cryptodb": 6,
    "piroplasmadb": 6,
    "tritrypdb": 6,
    "fungidb": 6,
    "vectorbase": 6,
    "giardiadb": 6,
    "amoebadb": 6,
    "microsporidiadb": 5,
    "hostdb": 6,
    "veupathdb": 6,
    "orthomcl": 5,
}
TOTAL_SEEDS = 76


def test_catalog_lists_every_json_file() -> None:
    on_disk = {p.name.removesuffix(".json") for p in SEEDS_DIR.iterdir()}
    assert on_disk == set(SEED_DATABASES)


def test_expected_counts_cover_every_database() -> None:
    assert set(EXPECTED_COUNTS) == set(SEED_DATABASES)


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_site_seed_count(site_id: str) -> None:
    assert len(get_seeds_for_site(site_id)) == EXPECTED_COUNTS[site_id]


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_every_seed_validates_and_names_its_own_site(site_id: str) -> None:
    for seed in get_seeds_for_site(site_id):
        assert isinstance(seed, SeedDef)
        assert seed.site_id == site_id
        assert seed.name
        assert seed.description
        assert seed.record_type in {"transcript", "group"}


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_every_control_set_has_positives_negatives_and_tags(site_id: str) -> None:
    incomplete = [
        seed.name
        for seed in get_seeds_for_site(site_id)
        if not (
            seed.control_set.name
            and seed.control_set.positive_ids
            and seed.control_set.negative_ids
            and seed.control_set.tags
            and seed.control_set.provenance_notes
        )
    ]

    assert incomplete == []


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_every_step_tree_builds_a_strategy_node(site_id: str) -> None:
    for seed in get_seeds_for_site(site_id):
        node = StrategyStepNode.model_validate(_coerce_step_tree_params(seed.step_tree))
        assert node.search_name


def test_get_all_seeds_totals_the_per_site_counts() -> None:
    assert len(get_all_seeds()) == TOTAL_SEEDS
    assert sum(EXPECTED_COUNTS.values()) == TOTAL_SEEDS


def test_unknown_site_raises_site_not_found() -> None:
    with pytest.raises(NotFoundError) as exc_info:
        get_seeds_for_site("nosuchdb")
    assert exc_info.value.code is ErrorCode.SITE_NOT_FOUND


def test_traversal_site_id_is_rejected_before_touching_the_filesystem() -> None:
    with pytest.raises(NotFoundError):
        get_seeds_for_site("../../../etc/passwd")


def test_seed_def_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SeedDef.model_validate(
            {
                "name": "x",
                "description": "x",
                "site_id": "plasmodb",
                "step_tree": {"searchName": "GenesByText"},
                "control_set": {
                    "name": "x",
                    "positive_ids": ["a"],
                    "negative_ids": ["b"],
                    "provenance_notes": "x",
                    "tags": ["t"],
                },
                "unexpected": 1,
            }
        )
