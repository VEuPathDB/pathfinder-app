"""A QA site served from a dev host, where the gene-model audit is offered."""

from __future__ import annotations

import pytest
from veupathdb.wdk import SiteInfo, get_site

from pathfinder.services.audit import offered

DEV_PLASMODB = "https://muharram.plasmodb.org/plasmo.amuharram/service"


def serve_plasmodb_from_a_dev_host(monkeypatch: pytest.MonkeyPatch) -> None:
    hosted = get_site("plasmodb").model_copy(update={"base_url": DEV_PLASMODB})

    def site(site_id: str) -> SiteInfo:
        return hosted if site_id == "plasmodb" else get_site(site_id)

    monkeypatch.setattr(offered, "get_site", site)
