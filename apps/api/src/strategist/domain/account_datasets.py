from __future__ import annotations

import re
from typing import Final

from veupathdb.wdk import EDA_USER_DATASET_PREFIX

_UPLOAD_ID: Final = re.compile(rf"{re.escape(EDA_USER_DATASET_PREFIX)}\w+")


def is_account_dataset(dataset_id: str) -> bool:
    return dataset_id.startswith(EDA_USER_DATASET_PREFIX)


def account_datasets_in(text: str) -> set[str]:
    return set(_UPLOAD_ID.findall(text))
