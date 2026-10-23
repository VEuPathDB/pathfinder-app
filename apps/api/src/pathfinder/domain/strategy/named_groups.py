from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import PhyleticExpression, PhyleticTree, species_of
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.words import words_of


class GroupScope(CamelModel):
    taxon: str = Field(
        description=(
            "The clade's code, as phyletic_expression writes it, or the full "
            "name of a genus, species or clade of the taxonomy, as the refusal "
            "that asks for the scope writes it."
        )
    )
    scope: Literal["whole", "named"] = Field(
        description=(
            "whole: the request means every genome of the taxon. named: the "
            "request means exactly the genomes the units name."
        )
    )
    except_codes: list[str] = Field(
        default_factory=list,
        description=(
            "With whole: the genome codes the request leaves out of the taxon."
        ),
    )


class NamedGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    taxon: str
    genomes: frozenset[str]

    def left_out(
        self, expressions: Sequence[PhyleticExpression], tree: PhyleticTree
    ) -> list[str]:
        named = {
            genome
            for expression in expressions
            for unit in expression.units()
            for genome in tree.genomes_under(unit.codes)
        }
        if not named & self.genomes:
            return []
        return [
            node.code
            for node in tree.nodes()
            if node.code in self.genomes and node.code not in named
        ]


def _key(taxon: str) -> str:
    return " ".join(words_of(taxon))


def _leaf_taxa(tree: PhyleticTree) -> dict[str, NamedGroup]:
    held: dict[str, tuple[str, set[str]]] = {}
    for node in tree.nodes():
        if not node.clade:
            species = species_of(node.label)
            for name in (species, " ".join(species.split()[:1])):
                held.setdefault(_key(name), (name, set()))[1].add(node.code)
    return {
        key: NamedGroup(name=name, taxon=name, genomes=frozenset(genomes))
        for key, (name, genomes) in held.items()
        if key
    }


def _resolved(taxon: str, tree: PhyleticTree) -> NamedGroup | None:
    clades = [
        NamedGroup(
            name=node.label,
            taxon=node.code,
            genomes=frozenset(tree.genomes_under([node.code])),
        )
        for node in tree.nodes()
        if node.clade
    ]
    coded = [clade for clade in clades if clade.taxon == taxon]
    named = [clade for clade in clades if _key(clade.name) == _key(taxon)]
    leaf = _leaf_taxa(tree).get(_key(taxon))
    found = coded or [*named, *([] if leaf is None else [leaf])]
    return found[0] if len(found) == 1 else None


def _present_codes(expressions: Sequence[PhyleticExpression]) -> set[str]:
    return {
        code
        for expression in expressions
        for unit in expression.units()
        if not (unit.op == "=" and unit.count == 0)
        for code in unit.codes
    }


def _species_of_leaves(tree: PhyleticTree) -> dict[str, str]:
    return {
        node.code: _key(species_of(node.label))
        for node in tree.nodes()
        if not node.clade
    }


def taxa_to_scope(
    expressions: Sequence[PhyleticExpression], tree: PhyleticTree
) -> list[NamedGroup]:
    leaves = _leaf_taxa(tree)
    written = _present_codes(expressions)
    genera: dict[str, dict[str, set[str]]] = {}
    for node in tree.nodes():
        if not node.clade and node.code in written:
            label = species_of(node.label)
            held = genera.setdefault(_key(label.split()[0]), {})
            held.setdefault(_key(label), set()).add(node.code)
    found: list[NamedGroup] = []
    for genus, species in genera.items():
        if len(species) > 1:
            found.append(leaves[genus])
        else:
            found += [leaves[name] for name, codes in species.items() if len(codes) > 1]
    return found


def merged_scopes(
    held: Mapping[str, GroupScope], stated: Sequence[GroupScope]
) -> dict[str, GroupScope]:
    restated = {_key(scope.taxon): scope for scope in stated}
    kept = {key: scope for key, scope in held.items() if key not in restated}
    return {**kept, **restated}


class ScopedTaxon(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: GroupScope
    group: NamedGroup
    held: bool

    @property
    def stray_codes(self) -> list[str]:
        return [
            code for code in self.scope.except_codes if code not in self.group.genomes
        ]

    @property
    def required(self) -> NamedGroup:
        if not self.scope.except_codes:
            return self.group
        return NamedGroup(
            name=f"{self.group.name} except {', '.join(self.scope.except_codes)}",
            taxon=self.group.taxon,
            genomes=self.group.genomes - set(self.scope.except_codes),
        )


def _spans(group: NamedGroup, written: set[str], species: Mapping[str, str]) -> bool:
    named = {species[code] for code in written & group.genomes}
    own = {species[code] for code in group.genomes}
    return len(named) > 1 or (len(own) == 1 and len(written & group.genomes) > 1)


def scoped_taxa(
    held: Mapping[str, GroupScope],
    stated: Sequence[GroupScope],
    expressions: Sequence[PhyleticExpression],
    tree: PhyleticTree,
) -> list[ScopedTaxon]:
    written = _present_codes(expressions)
    species = _species_of_leaves(tree)
    restated = {_key(scope.taxon) for scope in stated}
    found: dict[str, ScopedTaxon] = {}
    entries = [
        *((scope, True) for key, scope in held.items() if key not in restated),
        *((scope, False) for scope in stated),
    ]
    for scope, from_thread in entries:
        group = _resolved(scope.taxon, tree)
        if group is None or (from_thread and not _spans(group, written, species)):
            continue
        found.pop(group.taxon, None)
        found[group.taxon] = ScopedTaxon(scope=scope, group=group, held=from_thread)
    return list(found.values())


def unscoped_taxa(
    expressions: Sequence[PhyleticExpression],
    tree: PhyleticTree,
    scoped: Sequence[ScopedTaxon],
) -> list[NamedGroup]:
    return [
        group
        for group in taxa_to_scope(expressions, tree)
        if not any(group.genomes <= taxon.group.genomes for taxon in scoped)
    ]


def whole_taxa(scoped: Sequence[ScopedTaxon]) -> list[ScopedTaxon]:
    return [
        taxon
        for taxon in scoped
        if taxon.scope.scope == "whole" and taxon.required.genomes
    ]


__all__ = [
    "GroupScope",
    "NamedGroup",
    "ScopedTaxon",
    "merged_scopes",
    "scoped_taxa",
    "taxa_to_scope",
    "unscoped_taxa",
    "whole_taxa",
]
