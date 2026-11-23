from __future__ import annotations

from typing import Any

import pytest
from veupathdb.errors import WDKError

from strategist.domain.unread import Unread
from strategist.services.experiment import scored_comparison
from strategist.services.experiment.scored_comparison import run_scored_comparison
from strategist.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)
from strategist.services.experiment.variant_comparison import VariantSpec
from strategist.tests.unit.services.experiment.test_scored_comparison_reporting import (
    _POSITIVES,
    _variants,
    _wdk_validation_error,
)


async def test_a_failed_variant_whose_membership_read_fails_holds_it_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
        del config
        raise _wdk_validation_error()

    async def _search(site_id: str, spec: VariantSpec) -> Any:
        del site_id, spec
        msg = "Request failed after retries: ReadTimeout"
        raise WDKError(msg, status=502)

    monkeypatch.setattr(scored_comparison, "run_experiment", _run)
    monkeypatch.setattr(scored_comparison, "run_variant_search", _search)

    result = await run_scored_comparison(
        "plasmodb",
        "u1",
        _variants(),
        positive_controls=_POSITIVES,
        negative_controls=[],
    )

    assert [v.control_hits for v in result.variants] == [
        Unread(
            reason=(
                "HTTP 502: VEuPathDB service error: Request failed after retries: "
                "ReadTimeout"
            )
        )
    ] * 2
