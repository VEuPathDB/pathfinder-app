from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from strategist.ai.explore import explore_tools
from strategist.ai.explore.explore_tools import propose_readings
from strategist.domain.refusal import Problems, RefusalKey
from strategist.platform.refusals import ProblemsRefusal
from strategist.services.experiment.reading_count import ProposedReadingDraft
from strategist.services.experiment.variant_comparison import VariantInput, VariantSpec
from strategist.tests._support.explore_turns import SITE, serve_recorded_readings
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.explore.test_explore_proposes_whole_plans import (
    _CODING,
    _PEPTIDE,
)


def _bad(search: dict[str, Any], name: str, value: object) -> dict[str, Any]:
    return {**search, "parameters": {**search["parameters"], name: value}}


def _proposal(title: str, search: dict[str, Any]) -> ProposedReadingDraft:
    return ProposedReadingDraft.model_validate({"title": title, "searches": [search]})


def _counts_nothing(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    counted: list[object] = []

    async def _spy(*args: object) -> object:
        counted.append(args)
        raise AssertionError

    monkeypatch.setattr(explore_tools, "run_reading_count", _spy)
    return counted


_EXPORT = "GenesBySubcellularLocalizationpfal3D7_subcellular_localization_Cowman_RSRC"
_RECORDED_REFUSALS = {
    _EXPORT: (
        "geneListParam on GenesBySubcellularLocalizationpfal3D7_subcellular_"
        "localization_Cowman_RSRC has no entry that states ['Exported to the "
        "erythrocyte membrane']. Read its entries with get_parameter_options and "
        "pass one of them exactly."
    ),
    "GenesByOrthologPattern": (
        "included_species names no entry ['Plasmodium']. Nearest entries: "
        "['Plasmodium vivax PAM', 'Plasmodium vivax P01', 'Plasmodium vivax PvW1', "
        "'Plasmodium adleri G01', 'Plasmodium vivax Sal-1']."
    ),
}


def _search(label: str, search_name: str, name: str, value: str) -> dict[str, Any]:
    return {
        "label": label,
        "searchName": search_name,
        "parameters": {name: {"type": "single-pick-vocabulary", "value": value}},
    }


async def _refused_as_recorded(
    _ctx: object, search: VariantInput, *, record_type: str
) -> VariantSpec:
    del record_type
    key = RefusalKey(
        check="stated_value", criterion=search.label, search=search.search_name
    )
    raise ProblemsRefusal(Problems.one(key, _RECORDED_REFUSALS[search.search_name]))


async def test_two_proposals_with_a_bad_value_each_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(explore_tools, "resolved_search", _refused_as_recorded)
    counted = _counts_nothing(monkeypatch)
    ctx = lead_run_context(site_id=SITE)
    export = _search(
        "export",
        _EXPORT,
        "geneListParam",
        "Exported to the erythrocyte membrane",
    )
    conserved = _search(
        "conserved phylogeny",
        "GenesByOrthologPattern",
        "included_species",
        "Plasmodium",
    )

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(
            ctx, [_proposal("exported", export), _proposal("conserved", conserved)]
        )

    found = refused.value.problems.found
    assert [(p.key.criterion, p.sentence) for p in found] == [
        ("export", _RECORDED_REFUSALS[_EXPORT]),
        ("conserved phylogeny", _RECORDED_REFUSALS["GenesByOrthologPattern"]),
    ]
    assert counted == []
    assert ctx.deps.state.domain.offered_readings == {}


async def test_two_proposals_the_site_reads_a_bad_value_in_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    counted = _counts_nothing(monkeypatch)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(
            lead_run_context(site_id=SITE),
            [
                _proposal("peptides", _bad(_PEPTIDE, "signalp_version", "SignalP 99")),
                _proposal("coding", _bad(_CODING, "geneType", ["pseudo coding"])),
            ],
        )

    found = refused.value.problems.found
    assert [p.sentence.split(": ", 1)[0] for p in found] == ["peptide", "coding"]
    assert counted == []


async def test_two_proposals_of_one_plan_are_refused_before_any_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    counted = _counts_nothing(monkeypatch)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(
            lead_run_context(site_id=SITE),
            [
                _proposal("one", _PEPTIDE),
                _proposal("two", _PEPTIDE),
                _proposal("three", _bad(_CODING, "geneType", ["pseudo coding"])),
            ],
        )

    checks = [problem.key.check for problem in refused.value.problems.found]
    assert checks == ["stated_value", "proposal_plan"]
    assert counted == []


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
    readings = TypeAdapter(list[ProposedReadingDraft]).validate_python(
        json.loads(_RECORDED.read_text())["readings"]
    )

    async def _takes_no_weight(
        _ctx: object, search: VariantInput, *, record_type: str
    ) -> VariantSpec:
        del record_type
        key = RefusalKey(check="variant_parameters", search=search.search_name)
        said = f"{search.search_name} takes no parameter weight ({search.label})."
        raise ProblemsRefusal(Problems.one(key, said))

    monkeypatch.setattr(explore_tools, "resolved_search", _takes_no_weight)
    counted = _counts_nothing(monkeypatch)

    with pytest.raises(ProblemsRefusal) as refused:
        await propose_readings(lead_run_context(site_id=SITE), readings)

    [reading] = readings
    found = refused.value.problems.found
    assert [p.key.check for p in found] == [
        "proposal_shape",
        *["variant_parameters"] * 6,
    ]
    assert [p.sentence.rsplit("(", 1)[1] for p in found[1:]] == [
        "secreted).",
        "surface).",
        "blood-stage expression).",
        "sexual-stage expression).",
        "low variation).",
        "conserved across apicomplexans).",
    ]
    assert {p.key.criterion for p in found} == {reading.title}
    assert counted == []
