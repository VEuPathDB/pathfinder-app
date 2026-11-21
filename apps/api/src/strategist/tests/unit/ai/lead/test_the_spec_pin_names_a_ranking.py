from __future__ import annotations

from strategist.ai.lead.lead_pins import pinned_operational_spec
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.tests._support.run_context import lead_run_context

_RANKED = (
    "- ranked: a gene scores the sum of the weights of the searches that find "
    "it, and the result is sorted by score, highest first"
)


def _pin(*criteria: Criterion) -> list[str]:
    ctx = lead_run_context()
    ctx.deps.state.domain.operational_spec = OperationalSpec(
        goal="g", criteria=list(criteria)
    )
    return (pinned_operational_spec(ctx) or "").splitlines()


def test_a_weighted_spec_names_each_weight_and_the_ranking() -> None:
    lines = _pin(
        Criterion(id="c_a", text="a", search_name="GenesByText", weight=2),
        Criterion(id="c_b", text="b", search_name="GenesByText", weight=1),
    )

    assert (
        [line.rsplit(" | ", 1)[-1] for line in lines if line.startswith("  - [")],
        lines[-1],
    ) == (["weight 2", "weight 1"], _RANKED)


def test_an_unweighted_spec_names_no_ranking() -> None:
    lines = _pin(Criterion(id="c_a", text="a", search_name="GenesByText"))

    assert [line for line in lines if "weight" in line or "ranked" in line] == []
