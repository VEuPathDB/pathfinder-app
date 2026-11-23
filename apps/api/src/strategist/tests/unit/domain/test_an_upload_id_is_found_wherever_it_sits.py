from __future__ import annotations

import pytest

from strategist.domain.account_datasets import account_datasets_in, is_account_dataset
from strategist.domain.owner_reads import without_owner_reads

UPLOAD = "EDAUD_sF88g1cwo00gw"


@pytest.mark.parametrize(
    "text",
    [
        f"dataset_{UPLOAD}",
        f"foo{UPLOAD}",
        f"https://qa.plasmodb.org/plasmo/app/workspace/datasets/{UPLOAD}",
        f'The owner said "{UPLOAD}" holds the counts.',
    ],
)
def test_an_upload_id_is_found_wherever_it_sits(text: str) -> None:
    shown = without_owner_reads(
        [{"type": "source-url", "sourceId": "s-1", "url": text}]
    )

    assert account_datasets_in(text) == {UPLOAD}
    assert [UPLOAD in str(shown)] == [False]


def test_an_upload_id_is_its_prefix_and_a_curated_one_is_not() -> None:
    assert [is_account_dataset(UPLOAD), is_account_dataset("DS_53f554ec6a")] == [
        True,
        False,
    ]
