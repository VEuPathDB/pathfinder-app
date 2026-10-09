"""An added step's words name the search it runs, on every site."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.growths import added_growth
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import intersect_spec

_SITES = (
    "plasmodb",
    "toxodb",
    "cryptodb",
    "giardiadb",
    "amoebadb",
    "microsporidiadb",
    "piroplasmadb",
    "tritrypdb",
    "trichdb",
    "fungidb",
    "vectorbase",
    "hostdb",
    "veupathdb",
)


@pytest.mark.parametrize("site_id", _SITES)
def test_the_added_step_is_called_by_its_search(site_id: str) -> None:
    values = SiteValues.for_site(site_id)
    held = {c.search_name for c in intersect_spec(values).criteria}
    words = {
        "GenesByExportPrediction": "exported",
        "GenesByMolecularWeight": "molecular weight",
        "GenesByTaxon": values.organism,
    }

    (added,) = added_growth(values, held).criteria

    assert added.text == words[added.search_name]


@pytest.mark.parametrize(
    ("site_id", "search"),
    [
        ("plasmodb", "GenesByExportPrediction"),
        ("vectorbase", "GenesByMolecularWeight"),
        ("trichdb", "GenesByTaxon"),
    ],
)
def test_the_added_step_runs_the_first_search_the_site_carries(
    site_id: str, search: str
) -> None:
    values = SiteValues.for_site(site_id)
    held = {c.search_name for c in intersect_spec(values).criteria}

    (added,) = added_growth(values, held).criteria

    assert added.search_name == search
