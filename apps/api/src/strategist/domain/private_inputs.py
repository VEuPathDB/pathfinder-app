from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue
from veupathdb.domain.parameters import ParamValue, to_wire

from strategist.domain.account_datasets import account_datasets_in, is_account_dataset

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
    hidden_values: frozenset[str]
    account_reads: bool

    def names_account_data(self, text: str) -> bool:
        return any(value in text for value in self.hidden_values) or (
            not self.account_reads and bool(account_datasets_in(text))
        )

    def untyped[T: JsonValue](self, value: T, *, withheld: T) -> T:
        shown = self.account_reads and not self.names_account_data(json.dumps(value))
        return value if shown else withheld

    def hiding(self, values: frozenset[str]) -> ViewerInputs:
        return self.model_copy(update={"hidden_values": values})


class _StudyInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eda_dataset_id: str = ""


def _private_names(readable: Mapping[str, ParamValue]) -> set[str]:
    study = _StudyInput.model_validate(
        {name: to_wire(value) for name, value in readable.items()}
    )
    if is_account_dataset(study.eda_dataset_id):
        return set(readable)
    return {
        name for name, value in readable.items() if value.type in PRIVATE_INPUT_KINDS
    }


def inputs_for_viewer(
    parameters: Mapping[str, ParamValue], *, include_account_reads: bool
) -> ViewerInputs:
    readable = {
        name: value
        for name, value in parameters.items()
        if value.type not in OWNER_HANDLE_KINDS
    }
    private: set[str] = set() if include_account_reads else _private_names(readable)
    return ViewerInputs(
        shown={name: value for name, value in readable.items() if name not in private},
        withheld=sorted(private),
        hidden_values=frozenset(
            wire
            for name, value in parameters.items()
            if name not in readable or name in private
            if (wire := to_wire(value))
        ),
        account_reads=include_account_reads,
    )
