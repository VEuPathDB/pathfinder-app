"""Publishing a gene set to the researcher's VEuPathDB workspace.

Publication is opt-in and one-way: PathFinder keeps the set, and the VDI id it
records is a pointer to a durable artifact that lives on the site.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from veupathdb.wdk import (
    VdiDatasetDetails,
    VdiDatasetGoneError,
    VdiDatasetPostMeta,
    VdiDatasetPostResponse,
    VdiImportStatus,
    VdiInstallStatus,
    VdiUploadStatus,
    VdiVisibility,
)

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets import vdi
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.types import GeneSet

_OWNER = uuid4()
_VDI_ID = "soV5JEQEcF00p"
_DATASET_URL = f"https://plasmodb.org/plasmo/app/workspace/datasets/{_VDI_ID}"


def _set(**over: Any) -> GeneSet:
    base: dict[str, Any] = {
        "id": "gs-1",
        "user_id": _OWNER,
        "site_id": "plasmodb",
        "name": "Kinases with a signal peptide",
        "gene_ids": ["PF3D7_1133400", "PF3D7_0709000"],
        "source": "strategy",
    }
    base.update(over)
    return GeneSet(**base)


def _service(gs: GeneSet | None) -> GeneSetService:
    store = AsyncMock()
    store.aget = AsyncMock(return_value=gs)
    store.save = lambda value: None
    store._persist = AsyncMock()
    store.get = lambda entity_id: gs
    return GeneSetService(store)


class _FakeVdi:
    def __init__(self, details: VdiDatasetDetails | None = None) -> None:
        self.sent: list[VdiDatasetPostMeta] = []
        self.gene_ids: list[list[str]] = []
        self.read: list[str] = []
        self._details = details

    async def create_genelist(
        self, *, details: VdiDatasetPostMeta, gene_ids: list[str]
    ) -> VdiDatasetPostResponse:
        self.sent.append(details)
        self.gene_ids.append(list(gene_ids))
        return VdiDatasetPostResponse(dataset_id=_VDI_ID)

    async def get(self, vdi_id: str) -> VdiDatasetDetails:
        self.read.append(vdi_id)
        if self._details is None:
            raise VdiDatasetGoneError(vdi_id)
        return self._details


def _details(
    *,
    upload: VdiUploadStatus = VdiUploadStatus.SUCCESS,
    import_status: VdiImportStatus = VdiImportStatus.COMPLETE,
    install: VdiInstallStatus | None = VdiInstallStatus.COMPLETE,
) -> VdiDatasetDetails:
    status: dict[str, Any] = {
        "upload": {"status": upload.value},
        "import": {"status": import_status.value},
    }
    if install is not None:
        status["install"] = [
            {"installTarget": "PlasmoDB", "meta": {"status": install.value}}
        ]
    return VdiDatasetDetails.model_validate(
        {
            "datasetId": _VDI_ID,
            "name": "Kinases with a signal peptide",
            "summary": "2 genes",
            "visibility": "private",
            "owner": {"userId": 1},
            "created": datetime.now(UTC).isoformat(),
            "installTargets": ["PlasmoDB"],
            "type": {"name": "genelist", "version": "1.0", "category": "Gene List"},
            "status": status,
        }
    )


def _use(monkeypatch: pytest.MonkeyPatch, fake: _FakeVdi) -> None:
    monkeypatch.setattr(vdi, "get_vdi_client", lambda site_id: fake)


class TestPublishing:
    async def test_the_request_names_the_genelist_plugin_and_the_sites_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi()
        _use(monkeypatch, fake)
        gs = _set()

        published = await vdi.publish_to_vdi(
            _service(gs),
            _OWNER,
            "gs-1",
            name="Kinases",
            visibility=VdiVisibility.PRIVATE,
        )

        sent = fake.sent[0]
        assert sent.type.name == "genelist"
        assert sent.type.version == "1.0"
        assert sent.install_targets == ["PlasmoDB"]
        assert sent.name == "Kinases"
        assert sent.visibility is VdiVisibility.PRIVATE
        assert sent.origin == "direct-upload"
        assert fake.gene_ids == [["PF3D7_1133400", "PF3D7_0709000"]]
        assert published.vdi_id == _VDI_ID
        assert published.dataset_url == _DATASET_URL
        assert published.gene_count == 2

    async def test_the_summary_names_the_gene_count_and_pathfinder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi()
        _use(monkeypatch, fake)

        await vdi.publish_to_vdi(
            _service(_set()),
            _OWNER,
            "gs-1",
            name="Kinases",
            visibility=VdiVisibility.PRIVATE,
        )

        assert "2 genes" in fake.sent[0].summary
        assert "PathFinder" in fake.sent[0].summary

    async def test_the_returned_id_is_written_onto_the_gene_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi()
        _use(monkeypatch, fake)
        gs = _set()

        await vdi.publish_to_vdi(
            _service(gs),
            _OWNER,
            "gs-1",
            name="Kinases",
            visibility=VdiVisibility.PUBLIC,
        )

        assert gs.vdi_id == _VDI_ID
        assert fake.sent[0].visibility is VdiVisibility.PUBLIC

    async def test_a_set_held_by_another_user_is_not_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi()
        _use(monkeypatch, fake)

        with pytest.raises(NotFoundError):
            await vdi.publish_to_vdi(
                _service(_set()),
                uuid4(),
                "gs-1",
                name="Kinases",
                visibility=VdiVisibility.PRIVATE,
            )

        assert fake.sent == []


class TestReadingTheStatus:
    async def test_an_installed_dataset_reports_the_target_and_its_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi(_details())
        _use(monkeypatch, fake)

        status = await vdi.vdi_publication_status(
            _service(_set(vdi_id=_VDI_ID)), _OWNER, "gs-1"
        )

        assert fake.read == [_VDI_ID]
        assert status.vdi_id == _VDI_ID
        assert status.dataset_url == _DATASET_URL
        assert status.installed_targets == ["PlasmoDB"]
        assert status.installed is True
        assert status.is_terminal is True

    async def test_a_dataset_still_importing_is_not_installed_yet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi(_details(import_status=VdiImportStatus.QUEUED, install=None))
        _use(monkeypatch, fake)

        status = await vdi.vdi_publication_status(
            _service(_set(vdi_id=_VDI_ID)), _OWNER, "gs-1"
        )

        assert status.installed is False
        assert status.is_terminal is False
        assert status.import_status is VdiImportStatus.QUEUED
        assert status.installed_targets == []

    async def test_a_failed_install_is_terminal_and_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi(_details(install=VdiInstallStatus.FAILED_INSTALLATION))
        _use(monkeypatch, fake)

        status = await vdi.vdi_publication_status(
            _service(_set(vdi_id=_VDI_ID)), _OWNER, "gs-1"
        )

        assert status.installed is False
        assert status.is_terminal is True

    async def test_a_set_that_was_never_published_has_no_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi(_details())
        _use(monkeypatch, fake)

        with pytest.raises(NotFoundError):
            await vdi.vdi_publication_status(_service(_set()), _OWNER, "gs-1")

        assert fake.read == []

    async def test_a_dataset_deleted_on_the_site_clears_the_recorded_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeVdi(None)
        _use(monkeypatch, fake)
        gs = _set(vdi_id=_VDI_ID)

        with pytest.raises(NotFoundError):
            await vdi.vdi_publication_status(_service(gs), _OWNER, "gs-1")

        assert gs.vdi_id is None
