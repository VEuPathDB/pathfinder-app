from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from veupathdb.wdk import EDA_USER_DATASET_PREFIX

_UPLOAD_ID: Final = re.compile(rf"{re.escape(EDA_USER_DATASET_PREFIX)}\w+")
UPLOAD_WORDS: Final = "a private dataset"


def is_account_dataset(dataset_id: str) -> bool:
    return dataset_id.startswith(EDA_USER_DATASET_PREFIX)


def leaves(value: JsonValue) -> Iterator[str]:
    match value:
        case str():
            yield value
        case list():
            for item in value:
                yield from leaves(item)
        case dict():
            for key, item in value.items():
                yield key
                yield from leaves(item)
        case _:
            return


def account_datasets_in(value: JsonValue) -> set[str]:
    return {found for leaf in leaves(value) for found in _UPLOAD_ID.findall(leaf)}


class StudyNames(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    dataset_id: str = Field(default="", alias="datasetId")
    study_id: str = Field(default="", alias="studyId")
    analysis_id: str = Field(default="", alias="analysisId")
    study_display_name: str = Field(default="", alias="studyDisplayName")
    display_name: str = Field(default="", alias="displayName")
    purpose: str = ""

    def marks(self) -> set[str]:
        return {
            self.dataset_id,
            self.study_id,
            self.analysis_id,
            self.study_display_name,
            self.display_name,
            self.purpose,
        } - {""}


def names_any(value: JsonValue, marks: set[str]) -> bool:
    return any(mark in leaf for leaf in leaves(value) for mark in marks)


def _replaced(text: str, marks: set[str]) -> str:
    for mark in sorted(marks, key=len, reverse=True):
        text = text.replace(mark, UPLOAD_WORDS)
    return text


def scrubbed(value: JsonValue, marks: set[str]) -> JsonValue:
    match value:
        case str():
            return _replaced(value, marks)
        case list():
            return [scrubbed(item, marks) for item in value]
        case dict():
            return {
                _replaced(key, marks): scrubbed(item, marks)
                for key, item in value.items()
            }
        case _:
            return value
