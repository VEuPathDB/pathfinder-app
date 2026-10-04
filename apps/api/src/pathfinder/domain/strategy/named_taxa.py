"""The taxa of an organism tree, and the taxon a message names whose organisms
a pick takes."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import (
    FAKE_ALL_SENTINEL,
    WDKTreeBoxVocabNode,
    collect_leaf_terms,
)
from veupathdb.model import CamelModel
from veupathdb.wdk import WDKSearch

from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.domain.strategy.words import WORD, spelled_words

# A taxon groups organisms, so it holds at least two of them.
_FEWEST_ORGANISMS = 2


class NamedTaxon(CamelModel):
    """A taxon a message names, by the name the site gives it, and the count
    of organisms under it."""

    model_config = ConfigDict(frozen=True)

    name: str
    organisms: int = Field(ge=_FEWEST_ORGANISMS)

    def label(self) -> str:
        return f"{self.organisms} organisms"


class Taxon(CamelModel):
    """A parent entry of an organism tree or a genus, and the leaf terms under it."""

    model_config = ConfigDict(frozen=True)

    name: str
    leaves: frozenset[str]


class OrganismTree(CamelModel):
    """The taxa of one organism tree, the leaves under each parent entry's
    term, and the label of every entry."""

    model_config = ConfigDict(frozen=True)

    taxa: list[Taxon]
    parents: dict[str, frozenset[str]]
    labels: list[str]

    def _leaves(self, terms: Sequence[str]) -> frozenset[str]:
        """The leaves the terms select: a parent entry selects those under it."""
        return frozenset(
            leaf for term in terms for leaf in self.parents.get(term, {term})
        )

    def named(
        self, terms: Sequence[str], request_texts: Sequence[str]
    ) -> tuple[NamedTaxon, str] | None:
        """The taxon whose organisms the terms select, when a message names it
        whole, and the message's words that name it. A longer entry the message
        names at the same words is that entry, not the taxon."""
        leaves = self._leaves(terms)
        if len(leaves) < _FEWEST_ORGANISMS:
            return None
        fitting = {t.name for t in self.taxa if t.leaves == leaves}
        for message in request_texts:
            tokens = list(WORD.finditer(message))
            for stated in stated_organisms(message, [*self.labels, *fitting]):
                if stated.entry in fitting:
                    first, last = tokens[stated.start], tokens[stated.end - 1]
                    words = message[first.start() : last.end()]
                    return NamedTaxon(name=stated.entry, organisms=len(leaves)), words
        return None


def _nodes(node: WDKTreeBoxVocabNode) -> Iterator[WDKTreeBoxVocabNode]:
    """Every entry under the node, the synthetic root left out."""
    if node.data.term != FAKE_ALL_SENTINEL:
        yield node
    for child in node.children:
        yield from _nodes(child)


def _label(node: WDKTreeBoxVocabNode) -> str:
    return node.data.display or node.data.term


def _genera(leaves: Sequence[WDKTreeBoxVocabNode]) -> list[Taxon]:
    """Each genus the leaf labels begin with, and the leaves whose label does."""
    named: dict[str, str] = {}
    under: dict[str, set[str]] = {}
    for leaf in leaves:
        head = spelled_words(_label(leaf))[:1]
        if head:
            key = head[0].casefold()
            named.setdefault(key, head[0])
            under.setdefault(key, set()).add(leaf.data.term)
    return [
        Taxon(name=named[key], leaves=frozenset(terms)) for key, terms in under.items()
    ]


def _organism_tree(root: WDKTreeBoxVocabNode) -> OrganismTree:
    """The taxa of the tree: each parent entry, then each genus of its leaves."""
    nodes = list(_nodes(root))
    parents = {
        n.data.term: frozenset(collect_leaf_terms(n)) for n in nodes if n.children
    }
    return OrganismTree(
        taxa=[
            *(
                Taxon(name=_label(n), leaves=parents[n.data.term])
                for n in nodes
                if n.children
            ),
            *_genera([n for n in nodes if not n.children]),
        ],
        parents=parents,
        labels=[_label(n) for n in nodes],
    )


def organism_trees(definition: WDKSearch) -> dict[str, OrganismTree]:
    """The organism tree of each organism parameter the search draws as a tree."""
    trees: dict[str, OrganismTree] = {}
    for param in definition.parameters or []:
        match param.vocabulary:
            case WDKTreeBoxVocabNode() as root if param.is_organism:
                trees[param.name] = _organism_tree(root)
            case _:
                pass
    return trees


__all__ = ["NamedTaxon", "OrganismTree", "organism_trees"]
