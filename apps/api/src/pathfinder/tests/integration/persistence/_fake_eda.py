"""A stand-in for the EDA study service that a branch and a revert call."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaFilter,
    EdaNotFoundError,
    EdaPermissionEntry,
    EdaServerError,
    EdaSubsetDescriptor,
)

from pathfinder.services.eda import thread_surgery
from pathfinder.tests.integration.persistence._thread_surgery import EDA_DATASET


@dataclass
class FakeEda:
    """Stands in for the EDA analysis service: its documents and its calls."""

    documents: dict[str, list[EdaFilter]] = field(default_factory=dict)
    created: list[tuple[str, str]] = field(default_factory=list)
    patched: list[tuple[str, list[EdaFilter]]] = field(default_factory=list)
    refuse_create: bool = False
    fresh: int = 0
    user_study: bool = True
    """Whether the study is the researcher's own, which opens on every site."""

    def document(self, analysis_id: str, filters: Sequence[EdaFilter] = ()) -> str:
        """Register a document that already exists on the service."""
        self.documents[analysis_id] = list(filters)
        return analysis_id

    def _detail(self, analysis_id: str) -> EdaAnalysisDetail:
        if analysis_id not in self.documents:
            msg = f"GET /users/1/analyses/{analysis_id}: no such analysis"
            raise EdaNotFoundError(msg, 404)
        filters = self.documents[analysis_id]
        return EdaAnalysisDetail(
            analysis_id=analysis_id,
            study_id=EDA_DATASET,
            num_filters=len(filters),
            descriptor=EdaAnalysisDescriptor(
                subset=EdaSubsetDescriptor(descriptor=list(filters)),
            ),
        )

    async def open_analysis(
        self,
        site_id: str,
        *,
        dataset_id: str,
        display_name: str,
    ) -> str:
        del site_id
        if self.refuse_create:
            msg = "POST /users/1/analyses: the study service is unavailable"
            raise EdaServerError(msg, 503)
        self.fresh += 1
        analysis_id = f"fresh{self.fresh}"
        self.created.append((dataset_id, display_name))
        self.documents[analysis_id] = []
        return analysis_id

    async def patch_subset(
        self,
        site_id: str,
        *,
        analysis_id: str,
        dataset_id: str,
        filters: Sequence[EdaFilter],
    ) -> EdaAnalysisDetail:
        del site_id, dataset_id
        # A document that is gone refuses the patch, as the service does.
        self._detail(analysis_id)
        self.documents[analysis_id] = list(filters)
        self.patched.append((analysis_id, list(filters)))
        return self._detail(analysis_id)

    async def read_analysis(
        self,
        site_id: str,
        *,
        analysis_id: str,
    ) -> EdaAnalysisDetail:
        del site_id
        return self._detail(analysis_id)

    async def resolve_dataset(
        self, site_id: str, dataset_id: str
    ) -> EdaPermissionEntry:
        del site_id
        return EdaPermissionEntry(study_id=dataset_id, is_user_study=self.user_study)


def install_fake_eda(monkeypatch: pytest.MonkeyPatch) -> FakeEda:
    """Answer the study service from the test process."""
    fake = FakeEda()
    monkeypatch.setattr(thread_surgery, "open_analysis", fake.open_analysis)
    monkeypatch.setattr(thread_surgery, "patch_subset", fake.patch_subset)
    monkeypatch.setattr(thread_surgery, "read_analysis", fake.read_analysis)
    monkeypatch.setattr(thread_surgery, "resolve_dataset", fake.resolve_dataset)
    return fake
