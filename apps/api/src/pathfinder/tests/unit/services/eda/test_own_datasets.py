"""The researcher's own uploads on one site: VDI's owned listing joined to EDA's permissions."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.services.eda import catalog, private_datasets
from pathfinder.services.eda.private_datasets import (
    OwnDataset,
    OwnDatasets,
    own_datasets,
)
from pathfinder.tests._support.recorded_vdi import (
    RecordedPermissions,
    RecordedVdi,
    installed_user_study,
    permissions_body,
    vdi_body,
)

_INSTALLED = "4xZ5Q5pV1s4IM"
_INVALID = "MoZ5BBpM8U0IM"
_CRASHED = "lIZ5ZVpEVE0FE"
_GENE_LIST = "dMY5sYJRNl11F"


def _listing(*ids: str) -> list[Any]:
    """The recorded owned listing, cut to the rows named."""
    rows: list[Any] = vdi_body("datasets_owned")
    return [row for row in rows if row["datasetId"] in ids]


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("researcher.token")
    yield
    veupathdb_auth_token_ctx.reset(handle)


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    vdi: RecordedVdi,
    permissions: RecordedPermissions,
) -> None:
    monkeypatch.setattr(private_datasets, "get_vdi_client", lambda _site: vdi.client())
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: permissions.client())


def _by_id(datasets: list[OwnDataset]) -> dict[str, OwnDataset]:
    return {dataset.vdi_id: dataset for dataset in datasets}


async def test_an_installed_upload_with_a_permission_entry_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vdi = RecordedVdi(listing=_listing(_INSTALLED))
    _serve(
        monkeypatch, vdi, RecordedPermissions([permissions_body(with_user_study=True)])
    )

    found = await own_datasets("plasmodb")

    dataset_id, entry = installed_user_study()
    assert found.datasets == [
        OwnDataset(
            vdi_id=_INSTALLED,
            name="PathFinder live check stranded no label",
            created=datetime.fromisoformat("2026-09-24T08:02:05.971406-04:00"),
            state="installed",
            message=None,
            dataset_id=dataset_id,
            study_id=entry["studyId"],
            can_subset=True,
            can_export_rows=True,
        )
    ]
    assert dataset_id == f"EDAUD_{_INSTALLED}"


async def test_the_listing_is_read_for_this_sites_project_and_owned_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vdi = RecordedVdi(listing=_listing(_INSTALLED))
    _serve(
        monkeypatch, vdi, RecordedPermissions([permissions_body(with_user_study=True)])
    )

    await own_datasets("plasmodb")

    listing = next(r for r in vdi.requests if r.url.path == "/vdi/datasets")
    assert dict(listing.url.params) == {
        "install_target": "PlasmoDB",
        "ownership": "owned",
    }


async def test_an_upload_owned_on_another_site_only_is_not_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _listing(_INSTALLED)
    rows[0]["installTargets"] = ["ToxoDB"]
    rows[0]["status"]["install"][0]["installTarget"] = "ToxoDB"
    _serve(
        monkeypatch,
        RecordedVdi(listing=rows),
        RecordedPermissions([permissions_body(with_user_study=True)]),
    )

    found = await own_datasets("plasmodb")

    assert found.datasets == []


async def test_a_gene_list_is_not_a_study_and_is_not_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(
        monkeypatch,
        RecordedVdi(listing=_listing(_GENE_LIST)),
        RecordedPermissions([permissions_body(with_user_study=True)]),
    )

    found = await own_datasets("plasmodb")

    assert found.datasets == []


async def test_a_rejected_import_carries_vdis_message_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed row of the owned listing has no messages; the dataset's own read does."""
    detail = vdi_body("rnaseqrc_import_invalid")
    vdi = RecordedVdi(listing=_listing(_INVALID), statuses={_INVALID: [detail]})
    _serve(
        monkeypatch, vdi, RecordedPermissions([permissions_body(with_user_study=True)])
    )

    found = await own_datasets("plasmodb")

    failed = _by_id(found.datasets)[_INVALID]
    assert failed.state == "failed"
    assert failed.message == detail["status"]["import"]["messages"][0]
    assert failed.dataset_id is None
    assert f"GET /datasets/{_INVALID}" in vdi.calls()


async def test_only_a_failed_row_reads_the_dataset_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vdi = RecordedVdi(
        listing=_listing(_INSTALLED, _INVALID, _CRASHED),
        statuses={
            _INVALID: [vdi_body("rnaseqrc_import_invalid")],
            _CRASHED: [vdi_body("rnaseqrc_import_failed")],
        },
    )
    _serve(
        monkeypatch, vdi, RecordedPermissions([permissions_body(with_user_study=True)])
    )

    found = await own_datasets("plasmodb")

    reads = sorted(call for call in vdi.calls() if call.startswith("GET /datasets/"))
    assert reads == sorted([f"GET /datasets/{_CRASHED}", f"GET /datasets/{_INVALID}"])
    states = {vdi_id: row.state for vdi_id, row in _by_id(found.datasets).items()}
    assert states == {_INSTALLED: "installed", _INVALID: "failed", _CRASHED: "failed"}


async def test_the_newest_upload_comes_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The listing is served oldest first, so the order is this module's own."""
    vdi = RecordedVdi(
        listing=list(reversed(_listing(_INSTALLED, _INVALID))),
        statuses={_INVALID: [vdi_body("rnaseqrc_import_invalid")]},
    )
    _serve(
        monkeypatch, vdi, RecordedPermissions([permissions_body(with_user_study=True)])
    )

    found = await own_datasets("plasmodb")

    created = [row.created for row in found.datasets]
    assert created == sorted(created, reverse=True)
    assert [row.vdi_id for row in found.datasets] == [_INVALID, _INSTALLED]


async def test_the_list_links_the_sites_own_upload_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(
        monkeypatch,
        RecordedVdi(listing=[]),
        RecordedPermissions([permissions_body(with_user_study=False)]),
    )

    found = await own_datasets("plasmodb")

    assert found == OwnDatasets(
        datasets=[],
        upload_url="https://plasmodb.org/plasmo/app/workspace/datasets",
    )


async def test_a_study_the_map_lacks_reads_the_permissions_once_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install finished after this credential's map was read."""
    permissions = RecordedPermissions(
        [
            permissions_body(with_user_study=False),
            permissions_body(with_user_study=True),
        ]
    )
    _serve(monkeypatch, RecordedVdi(listing=_listing(_INSTALLED)), permissions)
    await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")

    found = await own_datasets("plasmodb")

    assert [(row.state, row.dataset_id) for row in found.datasets] == [
        ("installed", f"EDAUD_{_INSTALLED}")
    ]
    assert permissions.reads == 2


async def test_a_study_still_absent_after_the_second_read_is_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = RecordedPermissions([permissions_body(with_user_study=False)])
    _serve(monkeypatch, RecordedVdi(listing=_listing(_INSTALLED)), permissions)

    found = await own_datasets("plasmodb")

    assert [(row.state, row.message, row.dataset_id) for row in found.datasets] == [
        ("waiting", "Installed; the study is not visible yet.", None)
    ]
    assert permissions.reads == 2


async def test_a_study_the_map_holds_costs_no_second_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = RecordedPermissions([permissions_body(with_user_study=True)])
    _serve(monkeypatch, RecordedVdi(listing=_listing(_INSTALLED)), permissions)

    await own_datasets("plasmodb")

    assert permissions.reads == 1
