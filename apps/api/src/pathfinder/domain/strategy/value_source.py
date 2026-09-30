"""Who set a bound value: the request, a card, the site default or the model."""

from __future__ import annotations

from collections.abc import Sequence
from typing import assert_never

from pydantic import BaseModel, TypeAdapter
from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue, to_wire
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.log2_scale import (
    stated_on_the_other_scale,
    without_the_other_scale,
)
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.strategy.words import (
    FILLER_WORDS,
    WORD,
    whole_run_of,
    words_of,
)

_TERMS = TypeAdapter(list[str])
_PICKS = frozenset({"single-pick-vocabulary", "multi-pick-vocabulary"})
_SHORTEST_CUT_LABEL = 3
_SHORTEST_RELAXED_WORD = 6


class _NumberBounds(BaseModel):
    min: float | None = None
    max: float | None = None

    def texts(self) -> list[str]:
        return [
            NumberValue(value=b).to_wire()
            for b in (self.min, self.max)
            if b is not None
        ]


class _DateBounds(BaseModel):
    min: str | None = None
    max: str | None = None

    def texts(self) -> list[str]:
        return [b for b in (self.min, self.max) if b is not None]


def is_placeholder(value: ParamValue, info: ParameterInfo | None) -> bool:
    """Whether the parameter's sheet names the value a placeholder."""
    return info is not None and info.is_placeholder(to_wire(value))


def is_unset(
    value: ParamValue, initial_display_value: str | None, info: ParameterInfo | None
) -> bool:
    """Whether the value states nothing the site did not: a placeholder the
    parameter's sheet names, or the site's initial value."""
    return is_placeholder(value, info) or to_wire(value) == initial_display_value


def stated_texts(value: ParamValue) -> list[str]:
    """The texts one request message holds, each whole, to state the value.

    A filter, a dataset and a step are written by no researcher in words, so
    nothing states them.
    """
    match value.type:
        case "string" | "number" | "date" | "timestamp" | "single-pick-vocabulary":
            return [to_wire(value)]
        case "multi-pick-vocabulary":
            return _TERMS.validate_python(value.to_decoded())
        case "number-range":
            return _NumberBounds.model_validate_json(to_wire(value)).texts()
        case "date-range":
            return _DateBounds.model_validate_json(to_wire(value)).texts()
        case "filter" | "input-dataset" | "input-step":
            return []
        case _:
            assert_never(value.type)


def _number_of(value: ParamValue) -> float | None:
    """The number a numeric value or a numeric text holds, else None."""
    match value:
        case NumberValue(value=number):
            return float(number)
        case StringValue(value=text):
            try:
                return float(text)
            except ValueError:
                return None
        case _:
            return None


def _joined_run(prose: str, phrase: str) -> str:
    """The run of whole prose words whose letters and digits, joined, are the
    phrase's, in the prose's own spelling, else empty."""
    wanted = "".join(words_of(phrase))
    tokens = list(WORD.finditer(prose))
    held = [token.group().casefold() for token in tokens]
    for start in range(len(held)):
        joined = ""
        for end in range(start, len(held)):
            joined += held[end]
            if joined == wanted:
                return prose[tokens[start].start() : tokens[end].end()]
            if not wanted.startswith(joined):
                break
    return ""


def _run_of(prose: str, phrase: str) -> str:
    """The run of the prose that holds the phrase whole, its punctuation left
    out, in the prose's own spelling, else empty."""
    return whole_run_of(prose, phrase) or _joined_run(prose, phrase)


def stated_run(
    value: ParamValue, request_texts: Sequence[str], *, display_name: str = ""
) -> str:
    """The runs of the first request text that holds every text of the value
    whole, in the request's own spelling, else empty. A number written on the
    other scale than ``display_name`` names states the value it converts to."""
    number = _number_of(value)
    if number is not None:
        other = stated_on_the_other_scale(number, display_name, request_texts)
        if other:
            return other
    texts = stated_texts(value)
    for message in request_texts:
        held = without_the_other_scale(message, display_name)
        runs = [_run_of(held, text) for text in texts]
        if texts and all(runs):
            return ", ".join(runs)
    return ""


def _cut_by_one_word(words: list[str]) -> list[list[str]]:
    """The words with one word after the first left out, for each such word, in
    a label long enough to keep two words."""
    if len(words) < _SHORTEST_CUT_LABEL:
        return []
    return [[*words[:k], *words[k + 1 :]] for k in range(1, len(words))]


def _one_edit_apart(said: str, label_word: str) -> bool:
    """Whether one letter changed, added, left out or swapped with the next
    turns one word into the other."""
    if said == label_word or abs(len(said) - len(label_word)) > 1:
        return False
    head = next(
        (k for k, (a, b) in enumerate(zip(said, label_word, strict=False)) if a != b),
        min(len(said), len(label_word)),
    )
    swapped = said[head : head + 2][::-1] == label_word[head : head + 2]
    return (
        said[head + 1 :] == label_word[head + 1 :]
        or said[head:] == label_word[head + 1 :]
        or said[head + 1 :] == label_word[head:]
        or (swapped and said[head + 2 :] == label_word[head + 2 :])
    )


def _spelled_alike(said: str, label_word: str) -> bool:
    """A word of letters only, of six letters or more, may be one letter off."""
    return said == label_word or (
        said.isalpha()
        and label_word.isalpha()
        and min(len(said), len(label_word)) >= _SHORTEST_RELAXED_WORD
        and _one_edit_apart(said, label_word)
    )


def _names_words(said: Sequence[str], words: Sequence[str]) -> bool:
    """Whether the said words go word for word with the label's words, with at
    most one of them one letter off."""
    return (
        len(said) == len(words)
        and all(_spelled_alike(a, b) for a, b in zip(said, words, strict=True))
        and sum(a != b for a, b in zip(said, words, strict=True)) <= 1
    )


def _names_label(said: list[str], label: str) -> bool:
    words = words_of(label)
    return any(_names_words(said, form) for form in [words, *_cut_by_one_word(words)])


def _spelled_run(prose: str, words: list[str]) -> str:
    """The run of the prose that names the words, one of them possibly one
    letter off, in the prose's own spelling, else empty."""
    tokens = list(WORD.finditer(prose))
    held = [token.group().casefold() for token in tokens]
    size = len(words)
    for start in range(len(held) - size + 1):
        if size and _names_words(held[start : start + size], words):
            return prose[tokens[start].start() : tokens[start + size - 1].end()]
    return ""


def _label_run(message: str, label: str, vocabulary: Sequence[str]) -> str:
    """The run of the message that names the label whole, or without one word
    after its first, or with one long word one letter off, when those words
    name no other entry of a vocabulary that holds it."""
    whole = _run_of(message, label)
    if whole or label not in vocabulary:
        return whole
    words = words_of(label)
    others = [entry for entry in vocabulary if words_of(entry) != words]
    for form in [words, *_cut_by_one_word(words)]:
        run = _spelled_run(message, form)
        if run and not any(_names_label(words_of(run), entry) for entry in others):
            return run
    return ""


def stated_by_labels(
    labels: Sequence[str], vocabulary: Sequence[str], request_texts: Sequence[str]
) -> str:
    """The runs of the first request text that names every label the site gives
    a value, in the request's own spelling, else empty. ``vocabulary`` holds
    every label of the parameter, so words that name two entries name neither."""
    for message in request_texts:
        runs = [_label_run(message, label, vocabulary) for label in labels]
        if labels and all(runs):
            return ", ".join(runs)
    return ""


def _stem(word: str) -> str:
    return word.removesuffix("s")


def _beside(words: list[str], at: int, step: int) -> str:
    """The first word that is not filler from ``at`` in the direction of
    ``step``, else empty."""
    k = at + step
    while 0 <= k < len(words) and words[k] in FILLER_WORDS:
        k += step
    return words[k] if 0 <= k < len(words) else ""


def _names_the_parameter(
    shown: Sequence[str], request_texts: Sequence[str], display_name: str
) -> bool:
    """Whether a message writes one of the shown words beside a word of the
    parameter's display name that is none of them."""
    own = {_stem(word) for text in shown for word in words_of(text)}
    named = {_stem(word) for word in words_of(display_name)} - own - {""}
    for message in request_texts:
        words = words_of(message)
        for at, word in enumerate(words):
            if _stem(word) in own and (
                _stem(_beside(words, at, -1)) in named
                or _stem(_beside(words, at, 1)) in named
            ):
                return True
    return False


def stated_words(
    value: ParamValue,
    request_texts: Sequence[str],
    *,
    display_name: str = "",
    at_default: bool = False,
    labels: Sequence[str] = (),
    vocabulary: Sequence[str] = (),
) -> str:
    """The request's words that state the value, by its texts or its labels,
    else empty. A one-word pick at the site's initial value states only beside
    a word of the parameter's display name."""
    shown = list(labels) or stated_texts(value)
    one_word = all(len(words_of(text)) == 1 for text in shown)
    if (
        at_default
        and value.type in _PICKS
        and one_word
        and not _names_the_parameter(shown, request_texts, display_name)
    ):
        return ""
    return stated_run(
        value, request_texts, display_name=display_name
    ) or stated_by_labels(labels, vocabulary, request_texts)


def cut_from(value: ParamValue, requirement_phrases: Sequence[str]) -> str:
    """The part of a requirement phrase a text leaves words out of, in the
    phrase's own spelling, else empty. Words written before a text modify it,
    so a phrase that holds the text's words after a word that is not filler
    states a narrower text than the one bound."""
    match value:
        case StringValue(value=text):
            wanted = words_of(text)
        case _:
            return ""
    size = len(wanted)
    for phrase in requirement_phrases:
        tokens = list(WORD.finditer(phrase))
        held = [token.group().casefold() for token in tokens]
        for start in range(1, len(held) - size + 1):
            if size and held[start : start + size] == wanted:
                first = start
                while first > 0 and held[first - 1] not in FILLER_WORDS:
                    first -= 1
                if first < start:
                    end = tokens[start + size - 1].end()
                    return phrase[tokens[first].start() : end]
    return ""


def value_source(
    value: ParamValue,
    *,
    initial_display_value: str | None,
    request_texts: Sequence[str],
    info: ParameterInfo | None = None,
    card_value: str | None = None,
    display_name: str = "",
) -> ValueSource:
    """Who set one bound value, from data: the default for a placeholder, else
    stated, else the card's, else the default at the site's initial value, else
    chosen."""
    if is_placeholder(value, info):
        return "default"
    unset = is_unset(value, initial_display_value, info)
    if stated_words(value, request_texts, display_name=display_name, at_default=unset):
        return "stated"
    if card_value == to_wire(value):
        return "card"
    return "default" if unset else "chosen"
