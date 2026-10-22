"""A dataset value is a saved dataset id, the JSON of a dataset source, or typed ids."""

import pytest
from veupathdb.domain.parameters import InputDatasetValue, StringValue
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKDatasetConfigIdList, WDKDatasetIdListContent

from pathfinder.services.strategies.dataset_sources import dataset_source


def test_a_pasted_id_list_is_a_source() -> None:
    raw = '{"sourceType": "idList", "sourceContent": {"ids": ["PF3D7_1133400", "PF3D7_0709000"]}}'

    assert dataset_source("ds_gene_ids", InputDatasetValue(dataset_id=raw)) == (
        WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(
                ids=["PF3D7_1133400", "PF3D7_0709000"]
            ),
        )
    )


def test_a_strategy_source_takes_the_wdk_strategy_id() -> None:
    raw = '{"sourceType": "strategy", "sourceContent": {"strategyId": "330713643"}}'

    source = dataset_source("ds_gene_ids", InputDatasetValue(dataset_id=raw))

    assert source is not None
    assert source.model_dump(by_alias=True) == {
        "sourceType": "strategy",
        "sourceContent": {"strategyId": 330713643},
    }


def test_a_saved_dataset_id_is_not_a_source() -> None:
    sources = [
        dataset_source("ds_gene_ids", InputDatasetValue(dataset_id=saved))
        for saved in ("1", "330713643")
    ]

    assert sources == [None, None]


def test_a_value_of_another_kind_is_not_a_source() -> None:
    assert [dataset_source("organism", StringValue(value="{}"))] == [None]


@pytest.mark.parametrize(
    ("raw", "ids"),
    [
        ("PF3D7_1133400", ["PF3D7_1133400"]),
        ("PF3D7_1133400, PF3D7_0709000", ["PF3D7_1133400", "PF3D7_0709000"]),
        ("PF3D7_1133400;\nPF3D7_0709000\t", ["PF3D7_1133400", "PF3D7_0709000"]),
    ],
)
def test_typed_ids_are_split_as_the_site_splits_an_id_list(
    raw: str, ids: list[str]
) -> None:
    assert dataset_source("source_ids", InputDatasetValue(dataset_id=raw)) == (
        WDKDatasetConfigIdList(
            source_type="idList", source_content=WDKDatasetIdListContent(ids=ids)
        )
    )


@pytest.mark.parametrize("raw", ['{"sourceType": "idList"}', " ,; "])
def test_a_value_that_is_neither_is_refused(raw: str) -> None:
    with pytest.raises(ValidationError) as refused:
        dataset_source("ds_gene_ids", InputDatasetValue(dataset_id=raw))

    assert refused.value.status == 422
    assert refused.value.title == "The ID list is not one the site reads"
