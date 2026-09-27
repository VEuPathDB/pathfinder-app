"""The catalog reads that name a search's organism parameter, served offline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.wdk import WDKRecordType

from pathfinder.ai.tools.standalone import frame_structure
from pathfinder.services.strategies import organism_params, organism_universe

# The transcript record type as every genomic site publishes it.
TRANSCRIPT = WDKRecordType(
    url_segment="transcript",
    display_name="Gene",
    display_name_plural="Genes",
    short_display_name="Gene",
)


# The parameter each search marks as its organism, as plasmodb and vectorbase
# answer it; a search not named here marks none.
MARKS = {
    "GenesByTaxon": "organism",
    "GenesByOrthologs": "organism",
    "GenesWithSignalPeptide": "organism",
    "GenesByTransmembraneDomains": "organism",
    "GenesByExportPrediction": "organism",
    "GenesByGoTerm": "organism",
    "GenesByMolecularWeight": "organism",
    "GenesByText": "text_search_organism",
    "GenesByNgsSnps": "organismSinglePick",
    "GenesByLocation": "organismSinglePick",
    "GenesByGeneModelChars": "organism_select_none",
    "GenesByMassSpec": "ms_assay",
}


def serve_catalog_marks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the organism parameter of each search from ``MARKS``."""

    async def _record_type(_site: str, _search: str, hint: str | None) -> str:
        return hint or "transcript"

    async def _marked(_site: str, _record_type: str, search_name: str) -> str | None:
        return MARKS.get(search_name)

    monkeypatch.setattr(organism_params, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(organism_params, "organism_parameter", _marked)


def serve_organism_reads(
    monkeypatch: pytest.MonkeyPatch, organisms: Sequence[str]
) -> list[str]:
    """Serve the site's organisms and record types; each read is recorded."""
    reads: list[str] = []

    async def _organisms(site_id: str) -> list[str]:
        reads.append(f"organisms:{site_id}")
        return list(organisms)

    async def _record_types(site_id: str) -> list[WDKRecordType]:
        reads.append(f"record types:{site_id}")
        return [TRANSCRIPT]

    monkeypatch.setattr(frame_structure, "list_organisms", _organisms)
    monkeypatch.setattr(frame_structure, "get_raw_record_types", _record_types)
    return reads


def serve_universe_counts(
    monkeypatch: pytest.MonkeyPatch, genes: Mapping[tuple[str, ...], int | None]
) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Answer the site's organism search from ``genes``, empty cache first.

    Each read is recorded as its site, record type, search and organisms.
    """
    asked: list[tuple[str, str, str, tuple[str, ...]]] = []

    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> int | None:
        match params:
            case {"organism": MultiPickValue(values=values)}:
                asked.append((site_id, record_type, search_name, tuple(values)))
                return genes.get(tuple(values))
            case _:
                pytest.fail(f"the organism search was asked {dict(params)}")

    monkeypatch.setattr(organism_universe, "count_bound_criterion", _count)
    monkeypatch.setattr(organism_universe, "_UNIVERSE_COUNTS", {})
    return asked
