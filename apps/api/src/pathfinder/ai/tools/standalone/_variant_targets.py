"""What a variant is allowed to name.

A variant runs one WDK search. A combine step is a strategy structure, so it
has no search to run and WDK refuses it at execution time.
"""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME

from pathfinder.services.experiment.variant_comparison import VariantSpec

_COMBINE_NAMES = frozenset({COMBINE_SEARCH_NAME, "Combine", "combine"})


def reject_combine_variants(variants: list[VariantSpec]) -> None:
    """Raises ModelRetry when a variant names a combine step."""
    named = [v for v in variants if v.search_name in _COMBINE_NAMES]
    if not named:
        return
    offending = "; ".join(f"{v.label} ({v.search_name})" for v in named)
    msg = (
        f"These variants name a combine step rather than a WDK search — "
        f"{offending}. A combine step has no search to run. To test a combine "
        "step, call run_control_tests_on_step with its wdk_step_id. To compare "
        "variants, name the leaf search each one varies."
    )
    raise ModelRetry(msg)
