"""An arc binds the organism, the searches and the controls its site's seeds carry."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site


@pytest.mark.parametrize(
    ("site_id", "organism"),
    [
        ("vectorbase", "Anopheles gambiae PEST"),
        ("plasmodb", "Plasmodium falciparum 3D7"),
        ("toxodb", "Toxoplasma gondii ME49"),
        ("fungidb", "Aspergillus fumigatus Af293"),
        ("veupathdb", "Neospora caninum Liverpool"),
    ],
)
def test_the_organism_is_the_one_most_seed_searches_run_on(
    site_id: str, organism: str
) -> None:
    assert SiteValues.for_site(site_id).organism == organism


def test_the_controls_are_a_seed_control_set() -> None:
    control_set = get_seeds_for_site("vectorbase")[0].control_set

    controls = SiteValues.for_site("vectorbase").controls

    assert controls.name == control_set.name
    assert controls.positive_ids == control_set.positive_ids
    assert controls.negative_ids == control_set.negative_ids
    assert controls.positive_ids[0].startswith("AGAP")


def test_a_seed_search_carries_the_values_the_seed_ran() -> None:
    leaf = SiteValues.for_site("plasmodb").leaf("GenesWithSignalPeptide")

    assert leaf is not None
    assert leaf.values == {
        "organism": ["Plasmodium falciparum 3D7"],
        "signalp_version": "SignalP-6.0",
    }


def test_a_text_organism_is_bound_as_a_list() -> None:
    leaf = SiteValues.for_site("vectorbase").leaf("GenesByText")

    assert leaf is not None
    assert leaf.values["text_search_organism"] == ["Anopheles gambiae PEST"]


def test_the_searches_are_the_ones_the_seeds_run_on_the_site_organism() -> None:
    leaves = SiteValues.for_site("vectorbase").leaves

    assert [leaf.search_name for leaf in leaves] == [
        "GenesByText",
        "GenesByTransmembraneDomains",
        "GenesWithSignalPeptide",
        "GenesByMolecularWeight",
        "GenesByExonCount",
    ]


def test_the_portal_organisms_are_the_portal_seeds_most_run_first() -> None:
    assert SiteValues.for_site("vectorbase").portal_organisms[:3] == (
        "Neospora caninum Liverpool",
        "Trypanosoma cruzi CL Brener Esmeraldo-like",
        "Plasmodium vivax Sal-1",
    )


def test_the_portal_organisms_leave_out_the_site_organism() -> None:
    held = SiteValues.for_site("veupathdb")

    assert held.organism == "Neospora caninum Liverpool"
    assert held.portal_organisms[:2] == (
        "Trypanosoma cruzi CL Brener Esmeraldo-like",
        "Plasmodium vivax Sal-1",
    )
