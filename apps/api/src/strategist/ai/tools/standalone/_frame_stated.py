"""The values of one set_criterion call that the request's own words decide:
the organism entry it names or carries the genes to, and a text term it asks
for as a phrase."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from veupathdb.domain.parameters import (
    FAKE_ALL_SENTINEL,
    SHOWN_CANDIDATES,
    StringValue,
    WDKTreeBoxVocabNode,
    entry_name,
    match_exact_option,
    rank_entries,
)
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.constraints import Constraint
from strategist.domain.strategy.organism_phrases import stated_organisms
from strategist.domain.strategy.text_expression import unquoted_phrase_refusal
from strategist.domain.strategy.words import words_of
from strategist.services.strategies.parameter_rules import parameter_class
from strategist.services.strategies.record_classes import takes_an_input_step

# A binomial is a genus and a species epithet; a word after them names a strain.
_BINOMIAL_WORDS = 2


@dataclass(frozen=True)
class _OrganismTree:
    """Each entry's parent, and the entries at or under each entry."""

    parents: dict[str, str] = field(default_factory=dict)
    under: dict[str, frozenset[str]] = field(default_factory=dict)

    def above(self, entry: str, other: str) -> bool:
        """Whether the entry is an ancestor of the other."""
        return entry != other and other in self.under.get(entry, frozenset())

    def siblings(self, entry: str, other: str) -> bool:
        """Whether the two entries share a parent, or with no parent, the same
        genus and species words and a different strain."""
        if entry == other:
            return False
        parent = self.parents.get(entry)
        if parent is not None or self.parents.get(other) is not None:
            return parent == self.parents.get(other)
        head, other_head = words_of(entry), words_of(other)
        return (
            len(head) > _BINOMIAL_WORDS
            and len(other_head) > _BINOMIAL_WORDS
            and head[:_BINOMIAL_WORDS] == other_head[:_BINOMIAL_WORDS]
        )


def _read_tree(node: WDKTreeBoxVocabNode, tree: _OrganismTree) -> frozenset[str]:
    below = {node.data.term}
    for child in node.children:
        if node.data.term != FAKE_ALL_SENTINEL:
            tree.parents[child.data.term] = node.data.term
        below |= _read_tree(child, tree)
    tree.under[node.data.term] = frozenset(below)
    return tree.under[node.data.term]


def _organism_tree(definition: WDKSearch, name: str) -> _OrganismTree:
    """The organism tree; the synthetic root is no parent. A flat vocabulary
    has none."""
    tree = _OrganismTree()
    param = next((p for p in definition.parameters or [] if p.name == name), None)
    match None if param is None else param.vocabulary:
        case WDKTreeBoxVocabNode() as root:
            _read_tree(root, tree)
        case _:
            pass
    return tree


def _entries_stated(texts: Sequence[str], displays: Mapping[str, str]) -> list[str]:
    """The vocabulary values the texts state whole, in the order stated."""
    return [
        displays[s.entry]
        for text in texts
        for s in stated_organisms(text, list(displays))
    ]


def _an_organism_the_request_does_not_name(
    definition: WDKSearch,
    call: CriterionCall,
    info: ParameterInfo,
    requirements: Sequence[Constraint],
) -> str | None:
    """A bind that holds a sibling or an ancestor of an organism entry the
    request names whole, in place of that entry.

    The request names the site entries its live organism requirements hold: a
    value a later message replaced or withdrew is no longer named. A named entry is
    covered by itself and by any entry under it. A bound entry the request
    names, or one under it, is the request's own value and substitutes for
    nothing. An entry of another lineage belongs to another criterion and is
    never refused.
    """
    options = info.vocabulary()
    proposed = call.terms(info.name)
    bound = [term for v in proposed if (term := match_exact_option(options, v))]
    named = [
        term
        for c in requirements
        if c.organism is not None and (term := match_exact_option(options, c.organism))
    ]
    tree = _organism_tree(definition, info.name)
    unnamed = [b for b in bound if not any(b == n or tree.above(n, b) for n in named)]
    substituted = [
        n
        for n in named
        if not any(b == n or tree.above(n, b) for b in bound)
        and any(tree.siblings(n, b) or tree.above(b, n) for b in unnamed)
    ]
    if not substituted:
        return None
    return (
        f"{info.display_name} on {call.search_name} binds {proposed}, and the "
        f"request names {substituted[0]!r}, an entry of this vocabulary. Bind "
        "the entry the request names, or ask the researcher which one they mean."
    )


def _a_transform_to_another_organism(
    definition: WDKSearch, call: CriterionCall, info: ParameterInfo, carried_to: str
) -> str | None:
    """A transform bind that leaves out the organism entry the request carries
    the genes to, or any value outside that entry.

    A name the vocabulary lacks is named with the nearest entries.
    """
    options = info.vocabulary()
    proposed = call.terms(info.name)
    named = _entries_stated([carried_to], {o.display: o.value for o in options})
    if not named:
        nearest = [
            entry_name(o) for o in rank_entries(options, carried_to, SHOWN_CANDIDATES)
        ]
        return (
            f"{info.display_name} on {call.search_name} binds {proposed}, and the "
            f"request carries the genes to {carried_to!r}, which this vocabulary "
            f"lacks. Nearest entries: {nearest}. Bind the organism the request "
            "names, or ask the researcher which entry they mean."
        )
    bound = [term for v in proposed if (term := match_exact_option(options, v))]
    tree = _organism_tree(definition, info.name)
    if bound and all(any(b == n or tree.above(n, b) for n in named) for b in bound):
        return None
    return (
        f"{info.display_name} on {call.search_name} binds {proposed}, and the "
        f"request carries the genes to {named[0]!r}. A transform's organism is "
        "the organism of the genes it returns: bind the entry the request names."
    )


def _an_unquoted_phrase(
    call: CriterionCall, info: ParameterInfo, messages: Sequence[str]
) -> str | None:
    """A text term of several words sent unquoted when a request message asks
    for the phrase."""
    match call.values.get(info.name):
        case StringValue(value=text) if not info.is_placeholder(text):
            return unquoted_phrase_refusal(info.name, call.search_name, text, messages)
        case _:
            return None


def word_problems(
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
    state: AgentToolState,
) -> Problems:
    """An organism bind that leaves out the entry the request names or carries
    the genes to, and an unquoted text term the request asks for as a phrase,
    for every parameter.

    The live requirements decide the organism, and the request messages decide
    the phrase. A dependent organism parameter is checked once its parents are
    bound. A transform that carries the genes to an organism the bind leaves
    out is named for that organism alone.
    """
    carried_to = state.carried_to(call.criterion_id)
    transform = takes_an_input_step(definition)
    found: list[Problem] = []
    for info in infos:
        said: list[tuple[str, str | None]] = []
        if info.organism_param and not info.stated_parents:
            carried = (
                _a_transform_to_another_organism(definition, call, info, carried_to)
                if transform and carried_to
                else None
            )
            said.append(
                (Check.ORGANISM_CARRIED, carried)
                if carried is not None
                else (
                    Check.ORGANISM_NAMED,
                    _an_organism_the_request_does_not_name(
                        definition, call, info, state.stated_requirements
                    ),
                )
            )
        if parameter_class(info) == "string":
            said.append(
                (Check.PHRASE, _an_unquoted_phrase(call, info, state.request_messages))
            )
        found += [
            Problem(key=RefusalKey(check=check, parameter=info.name), sentence=s)
            for check, s in said
            if s is not None
        ]
    return Problems(found=tuple(found))
