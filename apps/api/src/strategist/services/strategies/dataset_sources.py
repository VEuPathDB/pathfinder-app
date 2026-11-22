"""Save a list of ids on the site as the dataset id the site reads."""

from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.wdk import (
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    get_strategy_api,
)
from veupathdb.wdk.wdk_models import WDKDatasetConfig


def id_list(ids: list[str]) -> WDKDatasetConfigIdList:
    return WDKDatasetConfigIdList(
        source_type="idList", source_content=WDKDatasetIdListContent(ids=ids)
    )


async def saved_dataset(site_id: str, source: WDKDatasetConfig) -> InputDatasetValue:
    dataset_id = await get_strategy_api(site_id).create_dataset(source)
    return InputDatasetValue(dataset_id=str(dataset_id))
