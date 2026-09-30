"""Who set each value a criterion binds, decided by the tool from data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType

from veupathdb.domain.parameters import (
    ParamKind,
    ParamValue,
    UnboundParameter,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._frame_rationale import ChosenWhy, SearchChoice
from pathfinder.domain.log2_scale import in_the_sites_scale, on_scale, scale_of
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.domain.strategy.value_source import (
    cut_from,
    is_placeholder,
    is_unset,
    stated_words,
    value_source,
)
from pathfinder.services.strategies.parameter_rules import rules_of

_NO_CARD: Mapping[str, BoundValue] = MappingProxyType({})
_TEXT: ParamKind = "string"


def _set_by_site(info: ParameterInfo | None) -> bool:
    return info is not None and rules_of(info).source == "site"


def bound_values(
    values: dict[str, ParamValue],
    *,
    infos: list[ParameterInfo],
    site_supplied: set[str],
    request_texts: list[str],
    reason: str,
    card_values: Mapping[str, BoundValue] = _NO_CARD,
    requirement_phrases: Sequence[str] = (),
) -> dict[str, BoundValue]:
    """Each resolved value with who set it. A value the site supplied is at its
    initial value; a value only the site sets is the default. ``card_values``
    holds what an answered card bound, each with the option id that bound it.
    A text that leaves words out of a requirement phrase is chosen, and names
    that phrase."""
    card_wire = {name: to_wire(held.value) for name, held in card_values.items()}
    by_name = {info.name: info for info in infos}
    bound: dict[str, BoundValue] = {}
    for name, value in values.items():
        info = by_name.get(name)
        initial = info.default_value if info is not None else None
        shown = info.display_name if info is not None else ""
        at_default = to_wire(value) if name in site_supplied else initial
        source = (
            "default"
            if _set_by_site(info)
            else value_source(
                value,
                initial_display_value=at_default,
                request_texts=request_texts,
                info=info,
                card_value=card_wire.get(name),
                display_name=shown,
            )
        )
        cut = cut_from(value, requirement_phrases)
        if source == "stated" and cut:
            source = "chosen"
        basis = {
            "stated": stated_words(
                value,
                request_texts,
                display_name=shown,
                at_default=is_unset(value, at_default, info),
            ),
            "chosen": reason,
            "card": card_values[name].basis if name in card_values else "",
        }.get(source, "")
        bound[name] = BoundValue(
            value=value,
            source=source,
            basis=basis,
            placeholder=is_placeholder(value, info),
            stated_as=cut if source == "chosen" else "",
        )
    return bound


def _number(proposal: str | list[str] | None) -> float | None:
    """The number a proposal of one text holds, else None."""
    match proposal:
        case str(text):
            try:
                return float(text)
            except ValueError:
                return None
        case _:
            return None


def on_the_sites_scale(
    call: CriterionCall, infos: list[ParameterInfo], request_texts: list[str]
) -> tuple[CriterionCall, list[str]]:
    """The call with each number the request writes on the other scale than its
    parameter's display name converted to that parameter's scale, and one
    correction for each."""
    shown = {info.name: info.display_name for info in infos}
    params = dict(call.params)
    corrections: list[str] = []
    for name, proposal in call.params.items():
        number = _number(proposal)
        site = scale_of(shown.get(name, ""))
        stated = (
            None
            if number is None or site is None
            else in_the_sites_scale(number, shown[name], request_texts)
        )
        if stated is None or site is None:
            continue
        converted = f"{on_scale(stated.number, stated.scale, site):g}"
        params[name] = converted
        corrections.append(
            f"{name} ({shown[name]}) takes a {site} value, so {stated.words!r} "
            f"binds as {converted}"
        )
    return replace(call, params=params), corrections


def _vocabulary_holding(labels: list[str], infos: list[ParameterInfo]) -> list[str]:
    """The labels of the first vocabulary that holds every one of these, else
    none."""
    for info in infos:
        held = [option.display for option in info.vocabulary()]
        if set(labels) <= set(held):
            return held
    return []


def stated_by_their_labels(
    bound: dict[str, BoundValue],
    labels: Sequence[Measurement],
    infos: list[ParameterInfo],
    request_texts: list[str],
) -> dict[str, BoundValue]:
    """The values with each one a request message names by the labels the site
    gives it recorded as stated, with those words as its basis. A value only
    the site sets is never stated."""
    by_name = {info.name: info for info in infos}
    restated = dict(bound)
    for name, held in bound.items():
        named = [m.label for m in labels if m.param == name and m.label]
        info = by_name.get(name)
        if held.source == "stated" or not named or _set_by_site(info):
            continue
        run = stated_words(
            held.value,
            request_texts,
            display_name="" if info is None else info.display_name,
            at_default=held.source == "default",
            labels=named,
            vocabulary=_vocabulary_holding(named, infos),
        )
        if run:
            restated[name] = held.model_copy(update={"source": "stated", "basis": run})
    return restated


def chosen_reason(why: SearchChoice | None, chosen: ChosenWhy) -> str:
    """The model's reason for the binding, or the reason the criterion held."""
    if why is not None:
        return why.reason
    match chosen.rationale:
        case SearchRationale(reason=reason):
            return reason
        case _:
            return ""


def card_values_of(spec: OperationalSpec, criterion_id: str) -> dict[str, BoundValue]:
    """The values an answered card bound on the criterion the draft holds."""
    return next((c.set_by("card") for c in spec.criteria if c.id == criterion_id), {})


def open_slots(
    criterion_id: str,
    slots: Sequence[UnboundParameter],
    infos: list[ParameterInfo],
) -> list[OpenSlot]:
    """Each parameter the binding left open, with the kind its sheet gives it.

    A parameter the sheet does not list takes text, as the site takes any value.
    """
    kinds: dict[str, ParamKind] = {info.name: info.param_kind for info in infos}
    return [
        OpenSlot(
            criterion_id=criterion_id,
            param_name=slot.param_name,
            param_kind=kinds.get(slot.param_name, _TEXT),
            question=slot.question,
            options=slot.options,
        )
        for slot in slots
    ]
