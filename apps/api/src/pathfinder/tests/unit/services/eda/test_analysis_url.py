"""The page where a site's study explorer opens one analysis."""

from __future__ import annotations

from pathfinder.services.eda.urls import analysis_url


def test_the_url_names_the_dataset_and_the_analysis_under_the_site_web_root() -> None:
    """The explorer route reads the WDK dataset id, not the EDA study id."""
    assert analysis_url(
        "vectorbase", dataset_id="DS_a91f666e84", analysis_id="C3WiXt0"
    ) == (
        "https://vectorbase.org/vectorbase/app/workspace/analyses/DS_a91f666e84/C3WiXt0"
    )
