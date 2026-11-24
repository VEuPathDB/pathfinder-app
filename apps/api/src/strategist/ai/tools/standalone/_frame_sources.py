"""Who set each value a criterion binds, decided by the tool from data."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from types import MappingProxyType

from veupathdb.domain.parameters import (
    NumberValue,
    ParamKind,
    ParamValue,
    StringValue,
    UnboundParameter,
    VocabOption,
    decimal_text,
)
from veupathdb.wdk import WDKSearch, WDKStringParam
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_rationale import ChosenWhy, SearchChoice
from strategist.domain.log2_scale import in_the_sites_scale, on_scale, scale_of
from strategist.domain.strategy.constraints import Constraint
from strategist.domain.strategy.expression_handles import stated_text
from strategist.domain.strategy.named_taxa import OrganismTree
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
    OpenSlot,
    OperationalSpec,
    RequirementLink,
)
from strategist.domain.strategy.stated_source import StatedSource
from strategist.domain.strategy.step_rationale import SearchRationale
from strategist.domain.strategy.value_binding import bind_values, pick_terms
from strategist.domain.strategy.value_source import (
    ParamSheet,
    cut_from,
    stated_source,
    stated_words,
    value_source,
)
from strategist.services.strategies.parameter_rules import rules_of

_NO_CARD: Mapping[str, BoundValue] = MappingProxyType({})
_NO_QUOTES: Mapping[str, Sequence[str]] = MappingProxyType({})
_NOTHING_TAKEN: Mapping[str, frozenset[str]] = MappingProxyType({})
_TEXT: ParamKind = "string"


def _vocabulary_of(info: ParameterInfo | None) -> list[VocabOption]:
    return [] if info is None else info.vocabulary()


def _set_by_site(info: ParameterInfo | None) -> bool:
    return info is not None and rules_of(info).source == "site"


def quotes_by_param(
    links: Sequence[RequirementLink], requirements: Sequence[Constraint]
) -> dict[str, list[str]]:
    quotes = {c.id: c.quote for c in requirements if c.quote}
    by_param: dict[str, list[str]] = {}
    for link in links:
        if link.param is not None and link.requirement in quotes:
            by_param.setdefault(link.param, []).append(quotes[link.requirement])
    return by_param


def bound_values(
    values: dict[str, ParamValue],
    *,
    infos: list[ParameterInfo],
    site_supplied: set[str],
    request_texts: list[str],
    reason: str,
    card_values: Mapping[str, BoundValue] = _NO_CARD,
    linked_quotes: Mapping[str, Sequence[str]] = _NO_QUOTES,
    taken: Mapping[str, frozenset[str]] = _NOTHING_TAKEN,
) -> dict[str, BoundValue]:
    """Each resolved value read on the published sheet, with who set it. A value
    the site supplied or only the site sets is the default; a text whose words
    no quote linked to its parameter writes is chosen."""
    card_held = {name: held.value for name, held in card_values.items()}
    by_name = {info.name: info for info in infos}
    bound: dict[str, BoundValue] = {}
    for name, held in bind_values(values, "default", infos).items():
        unset = held.unset or name in site_supplied
        info = by_name.get(name)
        source = (
            "default"
            if _set_by_site(info)
            else value_source(
                held.value,
                placeholder=held.placeholder,
                unset=unset,
                request_texts=request_texts,
                card_value=card_held.get(name),
                sheet=ParamSheet(
                    display_name=held.display_name,
                    vocabulary=tuple(_vocabulary_of(info)),
                    taken_elsewhere=taken.get(name, frozenset()),
                ),
            )
        )
        match source:
            case StatedSource() if not cut_from(
                held.value, linked_quotes.get(name, ()), request_texts
            ):
                bound[name] = held.sourced(source)
            case StatedSource() | "chosen":
                bound[name] = held.sourced("chosen", reason)
            case "card":
                bound[name] = held.sourced("card", card_values[name].basis)
            case "default":
                bound[name] = held.sourced("default")
    return bound


def _number(value: ParamValue) -> float | None:
    match value:
        case NumberValue(value=number):
            return number
        case StringValue(value=text):
            try:
                return float(text)
            except ValueError:
                return None
        case _:
            return None


def _on_scale(value: ParamValue, number: float) -> ParamValue:
    match value:
        case NumberValue():
            return NumberValue(value=number)
        case _:
            return StringValue(value=decimal_text(number))


def on_the_sites_scale(
    call: CriterionCall, infos: list[ParameterInfo], request_texts: list[str]
) -> tuple[CriterionCall, list[str]]:
    """The call with each number the request writes on the other scale than its
    parameter's display name converted to that parameter's scale, and one
    correction for each."""
    shown = {info.name: info.display_name for info in infos}
    converted: dict[str, ParamValue] = {}
    corrections: list[str] = []
    for name, value in call.values.items():
        number = _number(value)
        site = scale_of(shown.get(name, ""))
        stated = (
            None
            if number is None or site is None
            else in_the_sites_scale(number, shown[name], request_texts)
        )
        if stated is None or site is None:
            continue
        converted[name] = _on_scale(value, on_scale(stated.number, stated.scale, site))
        corrections.append(
            f"{name} ({shown[name]}) takes a {site} value, so {stated.words!r} "
            f"binds as {stated_text(name, converted[name])}"
        )
    return call.with_values(converted), corrections


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
    taken: Mapping[str, frozenset[str]] = _NOTHING_TAKEN,
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
            display_name=held.display_name,
            at_default=held.source == "default",
            labels=named,
            vocabulary=_vocabulary_holding(named, infos),
        )
        if run:
            restated[name] = held.sourced(
                stated_source(
                    held.value,
                    run,
                    request_texts,
                    _vocabulary_of(info),
                    taken_elsewhere=taken.get(name, frozenset()),
                ),
                held.basis,
            )
    return restated


def stated_by_their_taxa(
    bound: dict[str, BoundValue],
    trees: Mapping[str, OrganismTree],
    request_texts: list[str],
    infos: list[ParameterInfo],
    taken: Mapping[str, frozenset[str]] = _NOTHING_TAKEN,
) -> dict[str, BoundValue]:
    """The values with each organism pick whose taxon a message names recorded
    as stated, with that taxon and the words that name it. ``trees`` holds the
    organism tree of each organism parameter."""
    by_name = {info.name: info for info in infos}
    restated = dict(bound)
    for name, held in bound.items():
        tree = trees.get(name)
        if held.source == "stated" or tree is None:
            continue
        named = tree.named(pick_terms(held.value), request_texts)
        if named is not None:
            taxon, words = named
            vocabulary = _vocabulary_of(by_name.get(name))
            restated[name] = held.sourced(
                stated_source(
                    held.value,
                    words,
                    request_texts,
                    vocabulary,
                    taxon,
                    taken_elsewhere=taken.get(name, frozenset()),
                ),
                held.basis,
            )
    return restated


def restated_choices(
    held: dict[str, BoundValue],
    *,
    infos: list[ParameterInfo],
    labels: Sequence[Measurement],
    trees: Mapping[str, OrganismTree],
    request_texts: list[str],
    taken: Mapping[str, frozenset[str]],
) -> dict[str, BoundValue]:
    """The chosen values, each judged again against the entries every other
    criterion now binds, so a side of a comparison another criterion takes is
    stated."""
    by_name = {info.name: info for info in infos}
    chosen = {name: b for name, b in held.items() if b.source == "chosen"}
    for name, bound in chosen.items():
        match value_source(
            bound.value,
            placeholder=bound.placeholder,
            unset=bound.unset,
            request_texts=request_texts,
            sheet=ParamSheet(
                display_name=bound.display_name,
                vocabulary=tuple(_vocabulary_of(by_name.get(name))),
                taken_elsewhere=taken.get(name, frozenset()),
            ),
        ):
            case StatedSource() as stated if not cut_from(
                bound.value, (), request_texts
            ):
                chosen[name] = bound.sourced(stated, bound.basis)
            case _:
                pass
    labelled = stated_by_their_labels(chosen, labels, infos, request_texts, taken)
    named = stated_by_their_taxa(labelled, trees, request_texts, infos, taken)
    return {**held, **named}


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


def pasted_params(definition: WDKSearch) -> frozenset[str]:
    pasted: set[str] = set()
    for param in definition.parameters or []:
        match param:
            case WDKStringParam(is_multi_line=True):
                pasted.add(param.name)
            case _:
                continue
    return frozenset(pasted)


def open_slots(
    criterion_id: str,
    slots: Sequence[UnboundParameter],
    infos: list[ParameterInfo],
    pasted: Collection[str],
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
            pasted=slot.param_name in pasted,
            question=slot.question,
            options=slot.options,
        )
        for slot in slots
    ]
