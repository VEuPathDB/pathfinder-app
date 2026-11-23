from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from strategist.ai.explore import explore_tools
from strategist.ai.explore.explore_tools import propose_readings
from strategist.domain.refusal import Problems, RefusalKey
from strategist.platform.refusals import ProblemsRefusal, refusal_of
from strategist.services.experiment.reading_count import ProposedReading
from strategist.services.experiment.variant_comparison import VariantInput, VariantSpec
from strategist.tests._support.explore_turns import SITE, serve_recorded_readings
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.explore.test_explore_proposes_whole_plans import (
    _CODING,
    _PEPTIDE,
)


def _bad(search: dict[str, Any], name: str, value: object) -> dict[str, Any]:
    return {**search, "parameters": {**search["parameters"], name: value}}


def _proposal(title: str, search: dict[str, Any]) -> ProposedReading:
    return ProposedReading.model_validate({"title": title, "searches": [search]})


def _counts_nothing(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    counted: list[object] = []

    async def _spy(*args: object) -> object:
        counted.append(args)
        raise AssertionError

    monkeypatch.setattr(explore_tools, "run_reading_count", _spy)
    return counted


async def test_two_proposals_with_a_bad_value_each_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    counted = _counts_nothing(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(
            ctx,
            [
                _proposal("peptides", _bad(_PEPTIDE, "signalp_version", "SignalP 99")),
                _proposal("coding", _bad(_CODING, "geneType", ["pseudo coding"])),
            ],
        )

    titles = {problem.key.criterion for problem in refused.value.problems.found}
    assert titles == {"peptides", "coding"}
    assert counted == []
    assert ctx.deps.state.domain.offered_readings == {}


async def test_one_title_twice_and_a_bad_value_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    counted = _counts_nothing(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(
            ctx,
            [
                _proposal("same", _bad(_PEPTIDE, "signalp_version", "SignalP 99")),
                _proposal("same", _CODING),
            ],
        )

    checks = {problem.key.check for problem in refused.value.problems.found}
    assert checks == {"stated_value", "proposal_title"}
    assert counted == []


_RECORDED = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "proposals"
    / "weights_in_parameters.json"
)


async def test_a_plan_with_weights_in_its_parameters_names_every_fault_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = TypeAdapter(list[ProposedReading]).validate_python(
        json.loads(_RECORDED.read_text())["readings"]
    )

    async def _takes_no_weight(
        _ctx: object, search: VariantInput, *, record_type: str
    ) -> VariantSpec:
        del record_type
        raise refusal_of(
            Problems.one(
                RefusalKey(check="variant_parameters", search=search.search_name),
                f"{search.search_name} takes no parameter weight ({search.label}).",
            )
        )

    monkeypatch.setattr(explore_tools, "resolved_search", _takes_no_weight)
    counted = _counts_nothing(monkeypatch)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(lead_run_context(site_id=SITE), readings)

    checks = [problem.key.check for problem in refused.value.problems.found]
    assert checks == ["proposal_shape", *["variant_parameters"] * 6]
    assert counted == []
