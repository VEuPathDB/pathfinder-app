from __future__ import annotations

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.catalog import site_record_types

from strategist.tests._support.orthomcl_counts import ORTHOMCL_RECORD_TYPES

PLASMODB_RECORD_TYPES = [
    "transcript",
    "gene",
    "organism",
    "genomic-sequence",
    "genomic-segment",
    "strain-genomic-segment",
    "variation",
    "est",
    "pathway",
    "compound",
    "blast-est-ontology",
    "blast-orf-ontology",
    "file",
    "user-comment",
    "build",
    "junction",
    "dfile",
    "metrics",
    "jbrowse-gene",
    "dataset-release-notes",
    "legacy-dataset",
    "dataset",
    "datasource",
    "userdataset",
]


class _DeclaredRecordTypes:
    def held_record_types(self, site_id: str) -> list[WDKRecordType]:
        names = (
            ORTHOMCL_RECORD_TYPES if site_id == "orthomcl" else PLASMODB_RECORD_TYPES
        )
        return [WDKRecordType(url_segment=name) for name in names]


def serve_declared_record_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        site_record_types, "get_discovery_service", _DeclaredRecordTypes
    )


class _NoCatalog:
    def held_record_types(self, site_id: str) -> None:
        del site_id


class UnansweredRecordTypes:
    def __init__(self) -> None:
        self.reads = 0

    async def get_record_types(self) -> list[WDKRecordType]:
        self.reads += 1
        msg = "the site did not answer"
        raise WDKError(msg, status=502)


def serve_unanswered_record_types(
    monkeypatch: pytest.MonkeyPatch,
) -> UnansweredRecordTypes:
    site = UnansweredRecordTypes()
    monkeypatch.setattr(site_record_types, "_LISTED", {})
    monkeypatch.setattr(site_record_types, "get_discovery_service", _NoCatalog)
    monkeypatch.setattr(site_record_types, "get_wdk_client", lambda _site: site)
    return site
