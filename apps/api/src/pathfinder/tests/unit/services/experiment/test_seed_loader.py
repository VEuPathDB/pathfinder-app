"""Shape and count invariants of the JSON seed catalog."""

import datetime
import re

import pytest
from pydantic import ValidationError
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    SEEDS_DIR,
    get_all_seeds,
    get_seeds_for_site,
)
from pathfinder.services.experiment.seed.types import (
    ControlSetDef,
    SeedDef,
    SeedMeasurement,
)

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
    "trichdb": 2,
}
TOTAL_SEEDS = 78
_NODE_COUNT = re.compile(r"\b(\d+)-node\b")


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
    seeds = get_seeds_for_site(site_id)

    assert [seed.step_node().id for seed in seeds] == [
        seed.step_tree["id"] for seed in seeds
    ]


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


def _controls(positives: list[str], negatives: list[str]) -> dict[str, object]:
    return {
        "name": "x",
        "positive_ids": positives,
        "negative_ids": negatives,
        "provenance_notes": "x",
        "tags": ["t"],
    }


def _measured(**counts: object) -> dict[str, object]:
    return {
        "site_build": "69",
        "date": "2026-09-24",
        "positives_total": 2,
        "negatives_total": 1,
        **counts,
    }


def test_a_control_list_refuses_a_repeated_id() -> None:
    with pytest.raises(ValidationError, match="PF3D7_0102600"):
        ControlSetDef.model_validate(
            _controls(["PF3D7_0102600", "PF3D7_0102600"], ["PF3D7_0210100"])
        )


def test_a_control_on_both_lists_is_refused() -> None:
    with pytest.raises(ValidationError, match="PF3D7_0102600"):
        ControlSetDef.model_validate(
            _controls(["PF3D7_0102600"], ["PF3D7_0102600", "PF3D7_0210100"])
        )


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_a_stated_node_count_is_the_count_of_the_tree(site_id: str) -> None:
    def nodes(node: StrategyStepNode) -> int:
        inputs = (node.primary_input, node.secondary_input)
        return 1 + sum(nodes(one) for one in inputs if one is not None)

    stated = {
        seed.name: (
            [int(n) for n in _NODE_COUNT.findall(seed.description)],
            nodes(seed.step_node()),
        )
        for seed in get_seeds_for_site(site_id)
    }

    assert {
        name: said for name, (said, tree) in stated.items() if said not in ([], [tree])
    } == {}


def test_a_measurement_is_a_read_or_a_refusal() -> None:
    read = SeedMeasurement.model_validate(
        _measured(root_count=479, positives_recovered=2, negatives_admitted=0)
    )
    refused = SeedMeasurement.model_validate(_measured(refusal="no such search"))

    assert (read.recall, refused.recall) == (1.0, None)
    assert read.date == datetime.date(2026, 9, 24)
    with pytest.raises(ValidationError):
        SeedMeasurement.model_validate(_measured())
    with pytest.raises(ValidationError):
        SeedMeasurement.model_validate(
            _measured(
                root_count=479,
                positives_recovered=2,
                negatives_admitted=0,
                refusal="no such search",
            )
        )


def test_a_measurement_counts_the_seeds_own_controls() -> None:
    seed = {
        "name": "x",
        "description": "x",
        "site_id": "plasmodb",
        "step_tree": {"searchName": "GenesByText"},
        "control_set": _controls(["a", "b"], ["c", "d"]),
    }
    measured = _measured(root_count=10, positives_recovered=2, negatives_admitted=0)

    with pytest.raises(ValidationError, match="negatives"):
        SeedDef.model_validate({**seed, "measured": measured})
    assert SeedDef.model_validate(
        {**seed, "measured": {**measured, "negatives_total": 2}}
    ).measured


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_every_seed_carries_its_read(site_id: str) -> None:
    unmeasured = [
        seed.name for seed in get_seeds_for_site(site_id) if seed.measured is None
    ]

    assert unmeasured == []


@pytest.mark.parametrize("site_id", SEED_DATABASES)
def test_every_seed_recovers_every_positive_on_its_record(site_id: str) -> None:
    recalls = {
        seed.name: seed.measured.recall if seed.measured else None
        for seed in get_seeds_for_site(site_id)
    }

    assert recalls == dict.fromkeys(recalls, 1.0)
