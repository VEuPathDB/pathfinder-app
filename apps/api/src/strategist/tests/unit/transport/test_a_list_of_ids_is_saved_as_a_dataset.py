"""A list of ids the step editor sends is saved on the site as one dataset."""

from __future__ import annotations

import pytest
from veupathdb.wdk import WDKDatasetConfigIdList, WDKDatasetIdListContent
from veupathdb.wdk.wdk_models import WDKDatasetConfig

from strategist.services.strategies import dataset_sources
from strategist.transport.http.routers.sites.datasets import SavedDataset, save_dataset


class _Site:
    def __init__(self) -> None:
        self.saved: list[WDKDatasetConfig] = []

    async def create_dataset(self, source: WDKDatasetConfig) -> int:
        self.saved.append(source)
        return 9001


async def test_the_saved_list_answers_its_dataset_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site()
    monkeypatch.setattr(dataset_sources, "get_strategy_api", lambda _site_id: site)
    source = WDKDatasetConfigIdList(
        source_type="idList",
        source_content=WDKDatasetIdListContent(ids=["PF3D7_1133400"]),
    )

    saved = await save_dataset("plasmodb", source)

    assert (saved, site.saved) == (SavedDataset(dataset_id="9001"), [source])
    assert saved.model_dump(by_alias=True) == {"datasetId": "9001"}
