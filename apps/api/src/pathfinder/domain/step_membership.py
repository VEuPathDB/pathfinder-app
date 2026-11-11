from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.evidence import GeneFit, SampledGene

type Holding = Literal["in", "out", "unread"]

_SET_OPERATORS = frozenset(
    {
        CombineOp.INTERSECT,
        CombineOp.UNION,
        CombineOp.MINUS,
        CombineOp.LONLY,
        CombineOp.RMINUS,
        CombineOp.RONLY,
    }
)
_PRIMARY_SUBTRACTED = frozenset({CombineOp.RMINUS, CombineOp.RONLY})
_SECONDARY_SUBTRACTED = frozenset({CombineOp.MINUS, CombineOp.LONLY})


class StepHolds(CamelModel):
    model_config = ConfigDict(frozen=True)

    inside: frozenset[str] = frozenset()
    outside: frozenset[str] = frozenset()

    def holding(self, gene_id: str) -> Holding:
        if gene_id in self.inside:
            return "in"
        return "out" if gene_id in self.outside else "unread"


class StepFact(CamelModel):
    model_config = ConfigDict(frozen=True)

    title: str
    holding: Holding
    subtracted: bool = False

    @property
    def fits(self) -> GeneFit:
        if self.holding == "unread":
            return "unclear"
        return "yes" if (self.holding == "in") != self.subtracted else "no"

    @property
    def sentence(self) -> str:
        if self.holding == "unread":
            return f"The site did not say whether the step '{self.title}' holds it"
        where = "In" if self.holding == "in" else "Not in"
        subtracted = ", which the strategy subtracts" if self.subtracted else ""
        return f"{where} the step '{self.title}'{subtracted}"


class RequirementByStep(CamelModel):
    model_config = ConfigDict(frozen=True)

    requirement: str
    fits: GeneFit
    facts: list[StepFact]

    @property
    def sentence(self) -> str:
        return f"{' and '.join(f.sentence for f in self.facts)} ({self.requirement})"


class UnlistedStep(CamelModel):
    model_config = ConfigDict(frozen=True)

    requirement: str
    title: str
    count: int
    listed_at_most: int

    @property
    def sentence(self) -> str:
        return (
            f"The step '{self.title}' holds {self.count:,} genes, more than the "
            f"{self.listed_at_most:,} PathFinder lists, so the record judges "
            f"{self.requirement}"
        )


type Implied = Literal["in", "out"] | None

_IMPLIED_INPUTS: dict[tuple[CombineOp | None, Implied], tuple[Implied, Implied]] = {
    (CombineOp.INTERSECT, "in"): ("in", "in"),
    (CombineOp.UNION, "out"): ("out", "out"),
    (CombineOp.MINUS, "in"): ("in", "out"),
    (CombineOp.LONLY, "in"): ("in", "out"),
    (CombineOp.RMINUS, "in"): ("out", "in"),
    (CombineOp.RONLY, "in"): ("out", "in"),
}


def implied_holdings(
    node: StrategyStepNode, held: Implied = "in"
) -> dict[str, Implied]:
    primary, secondary = node.primary_input, node.secondary_input
    if primary is None or secondary is None:
        return {node.id: held}
    if node.operator not in _SET_OPERATORS:
        return {}
    left, right = _IMPLIED_INPUTS.get((node.operator, held), (None, None))
    return {**implied_holdings(primary, left), **implied_holdings(secondary, right)}


def _every_fit(fits: Iterable[GeneFit]) -> GeneFit:
    held = set(fits)
    if "no" in held:
        return "no"
    return "unclear" if "unclear" in held else "yes"


def _any_fit(fits: Iterable[GeneFit]) -> GeneFit:
    held = set(fits)
    if "yes" in held:
        return "yes"
    return "unclear" if "unclear" in held else "no"


def _facts(
    node: StrategyStepNode,
    linked: frozenset[str],
    facts: dict[str, StepFact],
    *,
    subtracted: bool,
) -> tuple[GeneFit, list[StepFact]] | None:
    primary, secondary = node.primary_input, node.secondary_input
    if primary is None or secondary is None:
        if node.id not in linked:
            return None
        fact = facts[node.id].model_copy(update={"subtracted": subtracted})
        return fact.fits, [fact]
    if node.operator not in _SET_OPERATORS:
        return None
    found = [
        part
        for part in (
            _facts(
                primary,
                linked,
                facts,
                subtracted=subtracted != (node.operator in _PRIMARY_SUBTRACTED),
            ),
            _facts(
                secondary,
                linked,
                facts,
                subtracted=subtracted != (node.operator in _SECONDARY_SUBTRACTED),
            ),
        )
        if part is not None
    ]
    if not found:
        return None
    joined = (
        _any_fit if (node.operator is CombineOp.UNION) != subtracted else _every_fit
    )
    return joined(f for f, _ in found), [fact for _, held in found for fact in held]


def requirement_by_steps(
    root: StrategyStepNode,
    requirement: str,
    linked: frozenset[str],
    facts: dict[str, StepFact],
) -> RequirementByStep:
    found = _facts(root, linked, facts, subtracted=False)
    if found is None:
        msg = f"no step the root reaches states {requirement!r}"
        raise ValueError(msg)
    fits, held = found
    return RequirementByStep(
        requirement=requirement,
        fits=fits,
        facts=[fact for fact in held if fact.fits == fits],
    )


def decided_by_steps(
    gene: SampledGene,
    decided: Sequence[RequirementByStep],
    unlisted: Sequence[UnlistedStep],
    *,
    judged: bool,
) -> SampledGene:
    if not decided and not unlisted:
        return gene
    fits: list[GeneFit] = [r.fits for r in decided]
    if judged:
        fits.append(gene.fits)
    return SampledGene(
        gene_id=gene.gene_id,
        product=gene.product,
        organism=gene.organism,
        fits=_every_fit(fits),
        why=". ".join(
            [
                *(["; ".join(r.sentence for r in decided)] if decided else []),
                *(u.sentence for u in unlisted),
                gene.why,
            ]
        ),
    )
