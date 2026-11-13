from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel

from strategist.domain.strategy.genome_group import GenomeGroup
from strategist.domain.strategy.readings import ReadValues
from strategist.domain.strategy.words import words_of


class SetValues(CamelModel):
    """An option that binds these wire values on one criterion."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["set_values"] = "set_values"
    criterion_id: str
    params: dict[str, str] = Field(min_length=1)


class Withdraw(CamelModel):
    """An option that withdraws one requirement, named by its id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["withdraw"] = "withdraw"
    constraint_id: str


class Keep(CamelModel):
    """An option that keeps one requirement as the thread holds it, by its id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["keep"] = "keep"
    constraint_id: str


class SetOrganism(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["set_organism"] = "set_organism"
    constraint_id: str
    organism: str = Field(min_length=1)


class SaveComputedGroups(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["save_computed_groups"] = "save_computed_groups"
    handle: str
    save: bool


class SetOperator(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["set_operator"] = "set_operator"
    criteria: list[str] = Field(min_length=2)
    operator: CombineOp


class ReadGenomes(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["read_genomes"] = "read_genomes"
    criterion_id: str
    group: GenomeGroup


class TailRule(CamelModel):
    model_config = ConfigDict(frozen=True)

    end: Literal["low", "high"]
    percent: Literal[5, 10]


class PickTail(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["pick_tail"] = "pick_tail"
    rule: TailRule
    variable_name: str = ""


class PickClass(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["pick_class"] = "pick_class"
    entity_id: str
    variable_id: str
    value: str


OptionBinding = Annotated[
    SetValues
    | ReadValues
    | Withdraw
    | Keep
    | SetOrganism
    | SaveComputedGroups
    | SetOperator
    | ReadGenomes
    | PickTail
    | PickClass,
    Discriminator("kind"),
]


class TypedOption(CamelModel):
    """One option a question card offers, and what answering it binds."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    binding: OptionBinding

    def offered_reading(self) -> ReadValues | None:
        match self.binding:
            case ReadValues() as read:
                return read
            case _:
                return None

    def values_bound(self) -> SetValues | None:
        match self.binding:
            case (
                SetValues(criterion_id=criterion_id, params=params)
                | ReadValues(criterion_id=criterion_id, params=params)
            ):
                return SetValues(criterion_id=criterion_id, params=params)
            case _:
                return None


def option_id(label: str) -> str:
    """The option's id: the words of its label, joined by hyphens."""
    return "-".join(words_of(label)) or label


def options_by_id(labels: Sequence[str]) -> dict[str, str]:
    """Each label under its id; a label whose id an earlier one holds is dropped."""
    found: dict[str, str] = {}
    for label in labels:
        if label:
            found.setdefault(option_id(label), label)
    return found


def binding_key(option: TypedOption) -> tuple[str, ...]:
    """What answering the option binds."""
    match option.binding:
        case (
            SetValues(criterion_id=criterion_id, params=params)
            | ReadValues(criterion_id=criterion_id, params=params)
        ):
            return (
                "set_values",
                criterion_id,
                *sorted(f"{k}={v}" for k, v in params.items()),
            )
        case Withdraw(constraint_id=key) | Keep(constraint_id=key):
            return (option.binding.kind, key)
        case SetOperator(criteria=criteria, operator=operator):
            return (option.binding.kind, *sorted(criteria), operator.value)
        case ReadGenomes(criterion_id=criterion_id, group=group):
            return (option.binding.kind, criterion_id, group.reading)
        case SetOrganism() | SaveComputedGroups() | PickTail() | PickClass():
            return (option.binding.kind, option.binding.model_dump_json())
