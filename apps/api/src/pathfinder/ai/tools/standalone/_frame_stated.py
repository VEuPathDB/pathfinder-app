"""The values of one set_criterion call that the request's own words decide:
the organism entry it names or carries the genes to, and a text term it asks
for as a phrase."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    FAKE_ALL_SENTINEL,
    MAX_NEAREST_ENTRIES,
    WDKTreeBoxVocabNode,
    match_exact_option,
    nearest_entries,
)
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.domain.strategy.text_expression import unquoted_phrase_refusal
from pathfinder.domain.strategy.words import words_of
from pathfinder.services.strategies.parameter_rules import parameter_class

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


def _refuse_an_organism_the_request_does_not_name(
    definition: WDKSearch,
    call: CriterionCall,
    info: ParameterInfo,
    requirements: Sequence[Constraint],
) -> None:
    """Refuse a bind that holds a sibling or an ancestor of an organism entry
    the request names whole, in place of that entry.

    The request names the organisms its live requirements state: a value a
    later message replaced or withdrew is no longer named. A named entry is
    covered by itself and by any entry under it. A bound entry the request
    names, or one under it, is the request's own value and substitutes for
    nothing. An entry of another lineage belongs to another criterion and is
    never refused.
    """
    options = info.vocabulary()
    proposed = proposal_values(call.params.get(info.name))
    bound = [term for v in proposed if (term := match_exact_option(options, v))]
    displays = {option.display: option.value for option in options}
    named = _entries_stated(
        [c.requested_value for c in requirements if c.kind is ConstraintKind.ORGANISM],
        displays,
    )
    tree = _organism_tree(definition, info.name)
    unnamed = [b for b in bound if not any(b == n or tree.above(n, b) for n in named)]
    substituted = [
        n
        for n in named
        if not any(b == n or tree.above(n, b) for b in bound)
        and any(tree.siblings(n, b) or tree.above(b, n) for b in unnamed)
    ]
    if substituted:
        msg = (
            f"{info.display_name} on {call.search_name} binds {proposed}, and the "
            f"request names {substituted[0]!r}, an entry of this vocabulary. Bind "
            "the entry the request names, or ask the researcher which one they mean."
        )
        raise ModelRetry(msg)


def _refuse_a_transform_to_another_organism(
    definition: WDKSearch, call: CriterionCall, info: ParameterInfo, carried_to: str
) -> None:
    """Refuse a transform bind that leaves out the organism entry the request
    carries the genes to, or any value outside that entry.

    A name the vocabulary lacks is refused with the nearest entries.
    """
    options = info.vocabulary()
    proposed = proposal_values(call.params.get(info.name))
    named = _entries_stated([carried_to], {o.display: o.value for o in options})
    if not named:
        nearest = nearest_entries(options, carried_to, MAX_NEAREST_ENTRIES)
        msg = (
            f"{info.display_name} on {call.search_name} binds {proposed}, and the "
            f"request carries the genes to {carried_to!r}, which this vocabulary "
            f"lacks. Nearest entries: {nearest}. Bind the organism the request "
            "names, or ask the researcher which entry they mean."
        )
        raise ModelRetry(msg)
    bound = [term for v in proposed if (term := match_exact_option(options, v))]
    tree = _organism_tree(definition, info.name)
    if not bound or not all(
        any(b == n or tree.above(n, b) for n in named) for b in bound
    ):
        msg = (
            f"{info.display_name} on {call.search_name} binds {proposed}, and the "
            f"request carries the genes to {named[0]!r}. A transform's organism is "
            "the organism of the genes it returns: bind the entry the request names."
        )
        raise ModelRetry(msg)


def _refuse_an_unquoted_phrase(
    call: CriterionCall, info: ParameterInfo, messages: Sequence[str]
) -> None:
    """Refuse a text term of several words sent unquoted when a request message
    asks for the phrase."""
    match call.params.get(info.name):
        case str() as text if not info.is_placeholder(text):
            refusal = unquoted_phrase_refusal(
                info.name, call.search_name, text, messages
            )
        case _:
            return
    if refusal is not None:
        raise ModelRetry(refusal)


def refuse_what_the_words_decide(
    definition: WDKSearch,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
    state: AgentToolState,
) -> None:
    """Refuse an organism bind that leaves out the entry the request names or
    carries the genes to, and an unquoted text term the request asks for as a
    phrase.

    The live requirements decide the organism, and the request messages decide
    the phrase. A dependent organism parameter is checked once its parents are
    bound.
    """
    carried_to = state.carried_to(call.criterion_id)
    transform = bool(definition.allowed_primary_input_record_class_names)
    for info in infos:
        if info.organism_param and not info.vocab_depends_on:
            _refuse_an_organism_the_request_does_not_name(
                definition, call, info, state.stated_requirements
            )
            if transform and carried_to:
                _refuse_a_transform_to_another_organism(
                    definition, call, info, carried_to
                )
        if parameter_class(info) == "string":
            _refuse_an_unquoted_phrase(call, info, state.request_messages)
