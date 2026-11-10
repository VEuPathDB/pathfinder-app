from __future__ import annotations

from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep

from pathfinder.domain.unrevisable_subset import unrevisable_subset_caveats

_GENERIC = "GenesByEdaSubset"


def _step(step_id: str, search: str, name: str) -> StrategyStep:
    return StrategyStep(
        id=step_id, kind=StepKind.SEARCH, search_name=search, display_name=name
    )


def test_a_step_on_the_generic_subset_search_says_the_site_cannot_revise_it() -> None:
    steps = {
        "step_a": _step("step_a", "GenesByOrthologPattern", "Ortholog pattern"),
        "step_b": _step("step_b", _GENERIC, "CRISPR screen subset"),
        "step_c": _step(
            "step_c",
            "GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC",
            "berghei subset",
        ),
    }

    assert [c.sentence for c in unrevisable_subset_caveats(steps, _GENERIC)] == [
        (
            "The site's Revise form cannot edit the dataset filter of "
            "'CRISPR screen subset'; ask PathFinder to change it."
        )
    ]
