from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from veupathdb.wdk import EDA_USER_DATASET_PREFIX

_UPLOAD_ID: Final = re.compile(rf"{re.escape(EDA_USER_DATASET_PREFIX)}\w+")
UPLOAD_WORDS: Final = "a private dataset"


def is_account_dataset(dataset_id: str) -> bool:
    return dataset_id.startswith(EDA_USER_DATASET_PREFIX)


def account_datasets_in(text: str) -> set[str]:
    return set(_UPLOAD_ID.findall(text))


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


def names_any(text: str, marks: set[str]) -> bool:
    return any(mark in text for mark in marks)


def scrubbed(value: JsonValue, marks: set[str]) -> JsonValue:
    match value:
        case str():
            for mark in sorted(marks, key=len, reverse=True):
                value = value.replace(mark, UPLOAD_WORDS)
            return value
        case list():
            return [scrubbed(item, marks) for item in value]
        case dict():
            return {key: scrubbed(item, marks) for key, item in value.items()}
        case _:
            return value
