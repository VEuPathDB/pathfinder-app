"""Links into a site's own EDA study explorer."""

from __future__ import annotations

from veupathdb.wdk import get_site


def analysis_url(site_id: str, *, dataset_id: str, analysis_id: str) -> str:
    """The explorer page of one analysis. The route names the WDK dataset id."""
    return (
        f"{get_site(site_id).web_base_url}/app/workspace/analyses/"
        f"{dataset_id}/{analysis_id}"
    )
