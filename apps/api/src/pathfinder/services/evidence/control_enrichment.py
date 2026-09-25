"""The hypergeometric row of a control result: positives among the returned controls."""

from __future__ import annotations

import math

from veupathdb_mcp.separation import hypergeometric_log_sf

from pathfinder.domain.evidence import (
    ControlEnrichment,
    ControlSetEvidence,
    ControlTestEvidence,
)


def control_enrichment(
    positive: ControlSetEvidence, negative: ControlSetEvidence
) -> ControlEnrichment:
    """The one-sided test of positives among the controls the target returned."""
    population = positive.controls_count + negative.controls_count
    returned = positive.returned_count + negative.returned_count
    log_sf = hypergeometric_log_sf(
        positive.returned_count, population, positive.controls_count, returned
    )
    return ControlEnrichment(
        population=population,
        positives=positive.controls_count,
        returned=returned,
        positives_returned=positive.returned_count,
        p_value=min(1.0, math.exp(log_sf)),
    )


def with_enrichment(tested: ControlTestEvidence) -> ControlTestEvidence:
    """The test with its hypergeometric row, when it ran both kinds."""
    positive, negative = tested.positive, tested.negative
    if positive is None or negative is None:
        return tested
    return tested.model_copy(
        update={"enrichment": control_enrichment(positive, negative)}
    )
