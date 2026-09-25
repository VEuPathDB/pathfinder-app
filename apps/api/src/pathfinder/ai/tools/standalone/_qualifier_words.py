"""The words of a criterion text, and what a WDK search definition can state.

Words are compared by a light stem, so a word and its plural or its adjective
read alike. Every set of words read here comes from WDK's own definitions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from veupathdb.domain.parameters import flatten_vocab
from veupathdb.wdk import WDKParameter, WDKSearch

# A stem shorter than this is a function word or a code, never a qualifier.
_MIN_STEM = 4
_SUFFIXES = (
    "ically",
    "ation",
    "ness",
    "ical",
    "ing",
    "ies",
    "ied",
    "ed",
    "es",
    "ic",
    "al",
    "ly",
    "e",
    "s",
    "y",
)
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NAME_PART = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")
_TAG = re.compile(r"<[^>]+>")
# A word after one of these, or under this prefix, is stated as absent.
_NEGATING = frozenset({"no", "not", "non", "without"})
_NEGATED_PREFIX = "non-"
# The option label that switches a yes/no parameter off.
_OFF = "no"
_INPUT_STEP = "input-step"
_FLAT_UNTIL = "typeAhead"


def proposal_values(proposal: str | list[str] | None) -> list[str]:
    """The values one parameter proposal names: none, one, or a list."""
    match proposal:
        case None:
            return []
        case str():
            return [proposal]
        case list():
            return proposal


def stem(word: str) -> str:
    """The word without the one suffix that leaves at least ``_MIN_STEM`` letters."""
    lowered = word.casefold()
    for suffix in _SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= _MIN_STEM:
            return lowered[: -len(suffix)]
    return lowered


def stems_of(text: str) -> set[str]:
    """The stem of every word of the text, markup left out."""
    words = _TOKEN.findall(_TAG.sub(" ", text).casefold())
    return {stem(part) for word in words for part in word.split("-") if part}


@dataclass(frozen=True)
class Qualifier:
    """A word of the criterion text, as written, and the stem it is read by."""

    word: str
    stem: str


def qualifiers_of(text: str) -> list[Qualifier]:
    """The words of the text that could narrow it, once each, in text order.

    A negated word states an absence, so it is not one of them.
    """
    found: list[Qualifier] = []
    previous = ""
    for token in _TOKEN.findall(text.casefold()):
        negated = token.startswith(_NEGATED_PREFIX) or previous in _NEGATING
        previous = token
        if negated or token in _NEGATING:
            continue
        for word in token.split("-"):
            read = stem(word)
            if (
                word.isalpha()
                and len(read) >= _MIN_STEM
                and read not in {q.stem for q in found}
            ):
                found.append(Qualifier(word=word, stem=read))
    return found


def the_one_search_naming(listing: Iterable[WDKSearch]) -> dict[str, str]:
    """Each stem exactly one of the record type's searches carries in a
    parameter name, and that search.

    A stem two or more searches carry, like the organism, is shared vocabulary,
    and a stem no search carries names nothing the site can state; neither is a
    qualifier.
    """
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for search in listing:
        for name in search.param_names:
            for part in _NAME_PART.split(name):
                if part:
                    owners[stem(part)].add(search.url_segment)
    return {
        word: next(iter(names)) for word, names in owners.items() if len(names) == 1
    }


def named_stems(definition: WDKSearch) -> frozenset[str]:
    """The stems of the search's own name and display name."""
    parts = _NAME_PART.split(definition.url_segment)
    return frozenset(stem(part) for part in parts if part) | stems_of(
        definition.display_name
    )


def spoken_stems(definition: WDKSearch) -> frozenset[str]:
    """Every stem the search's own definition uses: its names, its help, and
    the labels of every vocabulary it offers."""
    texts = [definition.display_name, definition.summary, definition.description]
    for param in definition.parameters or []:
        texts.extend([param.display_name, param.help or ""])
        texts.extend(option.display for option in flatten_vocab(param.vocabulary))
    return frozenset().union(*(stems_of(text) for text in texts))


@dataclass(frozen=True)
class Statement:
    """A visible parameter that can state a qualifier, and how.

    When the parameter's own name carries it, any value but ``off`` states it
    and ``terms`` is empty; otherwise ``terms`` are the options whose label
    carries it. ``terms`` and ``off`` hold each option by its term and its label.
    """

    name: str
    display_name: str
    terms: frozenset[str]
    off: frozenset[str]
    allowed: tuple[str, ...]

    def states(self, value: str | list[str] | None) -> bool:
        """Whether the proposed value states the qualifier."""
        chosen = set(proposal_values(value))
        if self.terms:
            return bool(chosen & self.terms)
        return bool(chosen - self.off)


def _flat_options(param: WDKParameter) -> list[tuple[str, str]]:
    """The (term, label) pairs of a vocabulary short enough to be a choice."""
    match param.vocabulary:
        case list() as terms if param.display_type != _FLAT_UNTIL:
            return [(t.term, t.display or t.term) for t in terms]
        case _:
            return []


def statements(
    definition: WDKSearch, wanted: str, *, besides: Sequence[str] = ()
) -> list[Statement]:
    """The visible parameters of the search that can state the stem.

    A parameter whose name is in ``besides`` is one the bound search also
    has, so it states nothing the bound search cannot.
    """
    found: list[Statement] = []
    for param in definition.parameters or []:
        if not param.is_visible or param.type == _INPUT_STEP or param.name in besides:
            continue
        options = _flat_options(param)
        named = wanted in stems_of(param.display_name)
        by_label = frozenset(
            value
            for t, label in options
            if not named and wanted in stems_of(label)
            for value in (t, label)
        )
        if not named and not by_label:
            continue
        off = frozenset(
            value
            for t, label in options
            if label.casefold() == _OFF
            for value in (t, label)
        )
        allowed = tuple(
            label
            for t, label in options
            if (t in by_label if by_label else t not in off)
        )
        found.append(
            Statement(
                name=param.name,
                display_name=param.display_name or param.name,
                terms=by_label,
                off=off,
                allowed=allowed,
            )
        )
    return found
