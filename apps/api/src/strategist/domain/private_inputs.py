from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.wdk import EDA_USER_DATASET_PREFIX

PRIVATE_INPUT_KINDS: Final[frozenset[str]] = frozenset({"input-dataset", "held"})
OWNER_HANDLE_KINDS: Final[frozenset[str]] = frozenset({"input-step"})
PUBLIC_INPUT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "string",
        "number",
        "number-range",
        "date",
        "date-range",
        "timestamp",
        "single-pick-vocabulary",
        "multi-pick-vocabulary",
        "filter",
    }
)


class ViewerInputs(BaseModel):
    model_config = ConfigDict(frozen=True)

    shown: dict[str, ParamValue]
    withheld: list[str]


class _StudyInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eda_dataset_id: str = ""


def is_account_dataset(dataset_id: str) -> bool:
    return dataset_id.startswith(EDA_USER_DATASET_PREFIX)


def inputs_for_viewer(
    parameters: Mapping[str, ParamValue], *, include_account_reads: bool
) -> ViewerInputs:
    readable = {
        name: value
        for name, value in parameters.items()
        if value.type not in OWNER_HANDLE_KINDS
    }
    if include_account_reads:
        return ViewerInputs(shown=readable, withheld=[])
    study = _StudyInput.model_validate(
        {name: to_wire(value) for name, value in readable.items()}
    )
    private = (
        set(readable)
        if is_account_dataset(study.eda_dataset_id)
        else {
            name
            for name, value in readable.items()
            if value.type in PRIVATE_INPUT_KINDS
        }
    )
    return ViewerInputs(
        shown={name: value for name, value in readable.items() if name not in private},
        withheld=sorted(private),
    )
