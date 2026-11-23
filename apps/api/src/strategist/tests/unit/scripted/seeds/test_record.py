"""The seed measurer writes a seed file in the layout it read it in, and the
organism marks the mock arcs read are recorded from the seeds' own searches."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from pydantic import SecretStr
from veupathdb_mcp.catalog import ValidatedParams
from veupathdb_mcp.controls import (
    ControlsSearch,
    ControlTargetData,
    ControlTestResult,
)

from strategist.platform.config import get_settings
from strategist.services.strategies import commit_tree
from strategist.tests._support.organism_reads import MARKS
from strategist.tests._support.record_classes import (
    list_each_search_under,
    list_searches_under,
)
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist_scripted.models import site_values
from strategist_scripted.seeds import record
from strategist_scripted.seeds.catalog import (
    MARKS_FILE,
    SEEDS_DIR,
    get_seeds_for_site,
    seed_databases,
)
from strategist_scripted.seeds.record import marks_json, seeds_json


@pytest.mark.parametrize("site_id", seed_databases())
def test_a_seed_file_is_written_back_byte_for_byte(site_id: str) -> None:
    on_disk = (SEEDS_DIR / f"{site_id}.json").read_text()

    assert seeds_json(get_seeds_for_site(site_id)) == on_disk


async def test_the_marks_are_recorded_for_every_search_the_seeds_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _record_type(_site: str, _search: str, hint: str | None) -> str:
        return hint or "transcript"

    async def _marked(_site: str, _record_type: str, search_name: str) -> str | None:
        return MARKS.get(search_name)

    monkeypatch.setattr(record, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(record, "organism_parameter", _marked)

    recorded = await record.seed_organism_marks()

    assert sorted(recorded) == sorted(seed_databases())
    assert recorded["trichdb"] == {
        "GenesByGoTerm": "organism",
        "GenesWithSignalPeptide": "organism",
    }
    assert set(recorded["vectorbase"]) == set(site_values.recorded_marks("vectorbase"))


def test_the_marks_file_is_written_back_byte_for_byte() -> None:
    on_disk = MARKS_FILE.read_text()

    assert marks_json(site_values.recorded_marks_by_site()) == on_disk


async def test_the_dev_login_signs_in_as_the_settings_dev_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wdk_dev_email", "dev@example.org")
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr("dev-password"))
    calls: list[tuple[str, str, str]] = []

    async def _login(site_id: str, email: str, password: str) -> str | None:
        calls.append((site_id, email, password))
        return "tok"

    monkeypatch.setattr(record, "password_login", _login)

    assert await record.dev_login("plasmodb") == "tok"
    assert calls == [("plasmodb", "dev@example.org", "dev-password")]


_PFAM = "GroupsByPFamIdOrKeyword"
_PATTERN = "GroupsByPhyleticPattern"


def _posted(api: RecordingWDK) -> list[str]:
    return [
        call.kwargs["record_type"]
        for call in api.calls
        if call.name in {"create_step", "create_combined_step"}
    ]


async def _as_stated(*_args: Any, **kwargs: Any) -> ValidatedParams:
    return ValidatedParams(params=dict(kwargs["stated"]))


async def test_a_group_seed_reads_its_controls_by_group_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tested: list[ControlsSearch] = []

    async def run(
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
        *,
        controls: ControlsSearch,
    ) -> ControlTestResult:
        del positive_controls, negative_controls
        tested.append(controls)
        return ControlTestResult(
            site_id=site_id,
            target=ControlTargetData(step_id=wdk_step_id, estimated_size=5),
        )

    api = RecordingWDK()
    for module in (record, commit_tree):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(record, "run_step_control_tests", run)
    monkeypatch.setattr(commit_tree, "validate_parameters", _as_stated)
    list_searches_under(monkeypatch, "group", [_PFAM, _PATTERN])
    (seed, *_) = get_seeds_for_site("orthomcl")

    await record.measure_seed(seed, "8.2", datetime.date(2026, 10, 22))

    assert (seed.record_type, _posted(api)) == ("group", ["group"] * 3)
    assert tested == [
        ControlsSearch(
            search_name="GroupsByNameList",
            param_name="group_names",
            record_type="group",
        )
    ]


async def test_a_seed_whose_leaves_the_site_lists_under_two_classes_posts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = RecordingWDK()
    for module in (record, commit_tree):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site: api)
    list_each_search_under(monkeypatch, {_PFAM: "sequence", _PATTERN: "group"})
    (seed, *_) = get_seeds_for_site("orthomcl")

    measured = await record.measure_seed(seed, "8.2", datetime.date(2026, 10, 22))

    assert _posted(api) == []
    assert measured.refusal is not None
    assert "joins two record types" in measured.refusal
