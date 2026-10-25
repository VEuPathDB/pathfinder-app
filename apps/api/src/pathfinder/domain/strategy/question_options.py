from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.readings import ReadValues
from pathfinder.domain.strategy.words import words_of


class SetValues(CamelModel):
    """An option that binds these wire values on one criterion."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["set_values"] = "set_values"
    criterion_id: str
    params: dict[str, str] = Field(min_length=1)


class Withdraw(CamelModel):
    """An option that withdraws one requirement, named by its key."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["withdraw"] = "withdraw"
    constraint_id: str


class Keep(CamelModel):
    """An option that keeps one requirement as the thread holds it, by its key."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["keep"] = "keep"
    constraint_id: str


class SaveComputedGroups(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["save_computed_groups"] = "save_computed_groups"
    handle: str
    save: bool


OptionBinding = Annotated[
    SetValues | ReadValues | Withdraw | Keep | SaveComputedGroups,
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
        case SaveComputedGroups(handle=handle, save=save):
            return (option.binding.kind, handle, str(save))


def refuse_a_single_option(question: str, labels: Sequence[str]) -> None:
    """A question that offers options offers a choice between two at least."""
    if len(labels) != 1:
        return
    msg = (
        f"the question {question!r} offers one option, {labels[0]!r}, which is no "
        f"choice: offer at least two values that each change something, or no "
        f"options for an answer in the researcher's words"
    )
    raise ValueError(msg)
