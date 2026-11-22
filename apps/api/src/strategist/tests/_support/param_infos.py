from __future__ import annotations

from collections.abc import Sequence

from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed


def organism_of(parameters: Sequence[WDKParameter]) -> str | None:
    return next((p.name for p in parameters if p.is_organism), None)


def sheet_of(parameters: Sequence[WDKParameter]) -> list[ParameterInfo]:
    return format_param_info_typed(list(parameters), organism=organism_of(parameters))
